"""Security tests for the agent foundations.

These tests are the specification of the security model: path escapes,
symlink tricks, secret files, shell injection, destructive commands,
permission escalation, and audit tampering must all be caught.
Run with:  pytest tests/test_agent_security.py
"""

import json
import os
from pathlib import Path

import pytest

from app.core.audit import GENESIS_HASH, AuditLogger, redact
from app.tools.command_policy import Decision, evaluate_command
from app.tools.path_guard import PathAccessError, PathGuard
from app.tools.permissions import (
    Capability,
    PermissionDeniedError,
    build_default_registry,
)
from app.tools.repo_reader import RepoReader


# ------------------------------------------------------------- fixtures ---


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """A small fake project, plus a secret OUTSIDE it we must never read."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("print('hello')\n")
    (root / "README.md").write_text("A demo project. TODO: add tests\n")
    (root / ".env").write_text("API_KEY=sk-verysecretkey1234567890\n")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[remote] url=https://x@host/r.git\n")

    outside_secret = tmp_path / "outside-secret.txt"
    outside_secret.write_text("host root password\n")
    return root


@pytest.fixture()
def audit(tmp_path: Path) -> AuditLogger:
    return AuditLogger(tmp_path / "audit.jsonl")


@pytest.fixture()
def reader(workspace: Path, audit: AuditLogger) -> RepoReader:
    return RepoReader(
        PathGuard(workspace),
        build_default_registry(audit),
        audit,
        max_read_bytes=10_000,
        max_tree_entries=100,
    )


READ = frozenset({Capability.READ_REPO})


# ------------------------------------------------------------ path guard ---


def test_guard_allows_normal_file(workspace: Path) -> None:
    guard = PathGuard(workspace)
    assert guard.resolve("src/main.py").name == "main.py"


def test_guard_blocks_dotdot_traversal(workspace: Path) -> None:
    guard = PathGuard(workspace)
    with pytest.raises(PathAccessError, match="outside"):
        guard.resolve("../outside-secret.txt")


def test_guard_blocks_deep_traversal(workspace: Path) -> None:
    guard = PathGuard(workspace)
    with pytest.raises(PathAccessError, match="outside"):
        guard.resolve("src/../../../etc/passwd")


def test_guard_blocks_absolute_path_escape(workspace: Path) -> None:
    guard = PathGuard(workspace)
    with pytest.raises(PathAccessError):
        guard.resolve("/etc/passwd")


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_guard_blocks_symlink_escape(workspace: Path, tmp_path: Path) -> None:
    """A symlink INSIDE the root pointing OUTSIDE must be denied."""
    link = workspace / "sneaky.txt"
    link.symlink_to(tmp_path / "outside-secret.txt")
    guard = PathGuard(workspace)
    with pytest.raises(PathAccessError, match="outside"):
        guard.resolve("sneaky.txt")


def test_guard_blocks_env_files(workspace: Path) -> None:
    guard = PathGuard(workspace)
    with pytest.raises(PathAccessError, match="secrets"):
        guard.resolve(".env")


def test_guard_blocks_git_internals(workspace: Path) -> None:
    guard = PathGuard(workspace)
    with pytest.raises(PathAccessError, match="off-limits"):
        guard.resolve(".git/config")


@pytest.mark.parametrize(
    "name", ["server.key", "cert.pem", "id_rsa", "aws-credentials.json"]
)
def test_guard_blocks_secret_looking_files(workspace: Path, name: str) -> None:
    (workspace / name).write_text("secret material")
    guard = PathGuard(workspace)
    with pytest.raises(PathAccessError):
        guard.resolve(name)


# ------------------------------------------------------------ repo reader ---


def test_tree_excludes_secret_and_git_files(reader: RepoReader) -> None:
    paths = {entry.path for entry in reader.list_tree(READ)}
    assert "src/main.py" in paths
    assert "README.md" in paths
    assert ".env" not in paths
    assert not any(path.startswith(".git") for path in paths)


def test_read_denied_without_capability(reader: RepoReader) -> None:
    with pytest.raises(PermissionDeniedError):
        reader.read_file("src/main.py", frozenset())


def test_read_file_within_bounds(reader: RepoReader) -> None:
    result = reader.read_file("src/main.py", READ)
    assert "hello" in result.content
    assert result.truncated is False


def test_read_refuses_binary(workspace: Path, reader: RepoReader) -> None:
    (workspace / "blob.bin").write_bytes(b"\x00\x01\x02")
    with pytest.raises(PathAccessError, match="binary"):
        reader.read_file("blob.bin", READ)


def test_oversized_read_is_truncated(workspace: Path, reader: RepoReader) -> None:
    (workspace / "big.txt").write_text("x" * 50_000)
    result = reader.read_file("big.txt", READ)
    assert result.truncated is True
    assert len(result.content) == 10_000


def test_search_finds_content(reader: RepoReader) -> None:
    hits = reader.search("TODO", READ)
    assert any(hit.path == "README.md" for hit in hits)


# --------------------------------------------------------- command policy ---


@pytest.mark.parametrize(
    "command",
    ["pytest -q", "ruff check .", "black --check .", "mypy app",
     "python -m pytest tests", "git status", "git diff", "git log --oneline",
     "npm test"],
)
def test_policy_allows_safe_commands(command: str) -> None:
    assert evaluate_command(command).decision is Decision.ALLOWED


@pytest.mark.parametrize(
    "command",
    ["rm -rf /", "sudo pytest", "env", "printenv", "curl http://evil.example",
     "bash -c anything", "git push origin main", "git merge feature",
     "git reset --hard", "git clean -fd", "dd if=x of=y",
     "/bin/rm file.txt", "python -c print(1)", "unknowntool --flag"],
)
def test_policy_blocks_dangerous_commands(command: str) -> None:
    assert evaluate_command(command).decision is Decision.BLOCKED


@pytest.mark.parametrize(
    "command",
    ["pytest; rm -rf /", "git status && curl evil", "pytest | tee out",
     "pytest > results.txt", "echo `whoami`", "pytest $(rm x)"],
)
def test_policy_blocks_shell_injection(command: str) -> None:
    result = evaluate_command(command)
    assert result.decision is Decision.BLOCKED
    assert "metacharacter" in result.reason


@pytest.mark.parametrize(
    "command",
    ["pip install requests", "npm install", "git commit -m msg",
     "git checkout -b feature/x"],
)
def test_policy_requires_approval_for_sensitive_commands(command: str) -> None:
    assert evaluate_command(command).decision is Decision.REQUIRES_APPROVAL


def test_policy_blocks_empty_command() -> None:
    assert evaluate_command("   ").decision is Decision.BLOCKED


# ------------------------------------------------------------ audit chain ---


def test_audit_chain_verifies_and_detects_tampering(tmp_path: Path) -> None:
    log = AuditLogger(tmp_path / "audit.jsonl")
    for index in range(5):
        log.record(actor="test", action=f"a{index}", outcome="ok")
    ok, message = log.verify_chain()
    assert ok, message

    # Tamper with line 3 and expect verification to fail.
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    record = json.loads(lines[2])
    record["action"] = "FORGED"
    lines[2] = json.dumps(record, separators=(",", ":"))
    (tmp_path / "audit.jsonl").write_text("\n".join(lines) + "\n")
    ok, message = log.verify_chain()
    assert not ok
    assert "3" in message


def test_audit_chain_detects_deleted_record(tmp_path: Path) -> None:
    log = AuditLogger(tmp_path / "audit.jsonl")
    for index in range(4):
        log.record(actor="test", action=f"a{index}", outcome="ok")
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    del lines[1]
    (tmp_path / "audit.jsonl").write_text("\n".join(lines) + "\n")
    ok, _ = log.verify_chain()
    assert not ok


def test_audit_resumes_chain_across_restart(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    AuditLogger(path).record(actor="a", action="one", outcome="ok")
    AuditLogger(path).record(actor="a", action="two", outcome="ok")  # new instance
    ok, message = AuditLogger(path).verify_chain()
    assert ok, message


def test_audit_redacts_secrets() -> None:
    dirty = {
        "api_key": "sk-abcdefghijklmnop1234",
        "note": "header was Bearer abcdefghijklmnop.qrstuvwxyz-12345",
        "nested": {"PASSWORD": "hunter2", "safe": "keep me"},
    }
    clean = redact(dirty)
    assert clean["api_key"] == "[REDACTED]"
    assert "Bearer" not in clean["note"] or "[REDACTED]" in clean["note"]
    assert clean["nested"]["PASSWORD"] == "[REDACTED]"
    assert clean["nested"]["safe"] == "keep me"


def test_audit_denied_reads_are_logged(
    reader: RepoReader, audit: AuditLogger
) -> None:
    with pytest.raises(PathAccessError):
        reader.read_file("../outside-secret.txt", READ)
    entries = [
        json.loads(line)
        for line in audit.path.read_text().splitlines()
        if line.strip()
    ]
    assert any(
        entry["action"] == "read_file" and entry["outcome"] == "denied"
        for entry in entries
    )
    assert entries[0]["prev_hash"] == GENESIS_HASH
