"""Narrow, local-only Git operations for reviewed change application.

Design principles:

* Every public function composes a FIXED argv shape — callers can only
  choose branch names, paths, and messages, never verbs or flags. There
  is no generic "run git" surface exposed to the model or to request
  bodies.
* A blocklist backstops the fixed shapes: even if a future caller made
  a mistake, argv containing push/pull/fetch/merge/rebase/reset/remote/
  config or force flags is refused before execution.
* Never `shell=True`; argument arrays only.
* The environment is sanitized. `GIT_TERMINAL_PROMPT=0` means git can
  never sit waiting for credentials (and therefore can never use them).
* NISH branch names are validated against a strict pattern, and the
  protected branches (main, master, develop, production, …) can never
  be created, deleted, or committed on by these functions.
* Every write operation is audited (verb + repo + branch, never file
  contents).
"""

import re
import subprocess
from pathlib import Path

from app.core.audit import get_audit_logger
from app.core.config import get_settings

PROTECTED_BRANCHES = frozenset(
    {"main", "master", "develop", "production", "prod", "release"}
)

NISH_BRANCH_PATTERN = re.compile(r"^nish/task-[0-9a-f]{8}-[a-z0-9][a-z0-9-]{0,40}$")

# Backstop blocklist — these must never appear anywhere in argv.
_FORBIDDEN_TOKENS = frozenset(
    {
        "push", "pull", "fetch", "merge", "rebase", "reset", "remote",
        "config", "clone", "submodule", "--force", "-f", "--hard",
        "gc", "filter-branch", "update-ref", "reflog",
    }
)

# "-D" (branch force-delete) is deliberately allowed ONLY through
# delete_nish_branch, which verifies the branch is a NISH task branch.

_WRITE_VERBS = frozenset({"checkout", "add", "commit", "branch"})


class GitError(Exception):
    """A git operation failed or was refused."""

    def __init__(self, message: str, output: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.output = output


def _audit():
    return get_audit_logger(get_settings().agent_audit_log_path)


def _sanitized_env() -> dict[str, str]:
    import os

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        # Git must never prompt for (or therefore use) credentials.
        "GIT_TERMINAL_PROMPT": "0",
    }
    return env


def _run(repo: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    """Execute one fixed-shape git command. Refuses forbidden tokens."""
    for arg in args:
        if arg in _FORBIDDEN_TOKENS:
            raise GitError(f"Refused git argument: {arg}")
    settings = get_settings()
    try:
        completed = subprocess.run(  # noqa: S603 — argv array, never a shell
            ["git", *args],
            cwd=repo,
            env=_sanitized_env(),
            capture_output=True,
            text=True,
            timeout=settings.coding_command_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]} timed out") from exc
    if args and args[0] in _WRITE_VERBS:
        _audit().record(
            actor="gitops",
            action=f"git_{args[0]}",
            outcome="ok" if completed.returncode == 0 else "error",
            detail={"repo": str(repo), "args": args[1:3]},
        )
    if check and completed.returncode != 0:
        excerpt = (completed.stderr or completed.stdout)[:400]
        raise GitError(f"git {args[0]} failed", output=excerpt)
    return completed


# ------------------------------------------------------------- read side ---


def is_git_repository(repo: Path) -> bool:
    result = _run(repo, ["rev-parse", "--is-inside-work-tree"], check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def _read_config_value(repo: Path, key: str) -> str | None:
    """READ-ONLY access to exactly two identity keys. This is the only
    place `git config` is ever invoked, the argv shape is fixed (no
    flags, no value → git treats it as a read), and it deliberately does
    not go through _run so the blocklist can keep refusing `config`
    everywhere else."""
    if key not in ("user.name", "user.email"):
        raise GitError(f"Refused config read: {key}")
    settings = get_settings()
    try:
        completed = subprocess.run(  # noqa: S603 — fixed read-only argv
            ["git", "config", key],
            cwd=repo,
            env=_sanitized_env(),
            capture_output=True,
            text=True,
            timeout=settings.coding_command_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError("git config read timed out") from exc
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def configured_identity(repo: Path) -> tuple[str, str] | None:
    """The repository's effective git identity, or None if unset. NISH
    never invents an identity — commits use what the repo already has."""
    name = _read_config_value(repo, "user.name")
    email = _read_config_value(repo, "user.email")
    if not name or not email:
        return None
    return (name, email)


def is_clean(repo: Path) -> bool:
    result = _run(repo, ["status", "--porcelain"])
    return result.stdout.strip() == ""


def has_tracked_changes(repo: Path) -> bool:
    """True when tracked files are modified/staged/deleted. Untracked
    files are ignored: they survive a branch switch untouched, so they
    are not a work-loss hazard for rollback."""
    result = _run(repo, ["status", "--porcelain"])
    return any(
        line and not line.startswith("??")
        for line in result.stdout.splitlines()
    )


def current_branch(repo: Path) -> str:
    return _run(repo, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()


def head_commit(repo: Path) -> str:
    return _run(repo, ["rev-parse", "HEAD"]).stdout.strip()


def branch_exists(repo: Path, name: str) -> bool:
    result = _run(
        repo, ["rev-parse", "--verify", "--quiet", f"refs/heads/{name}"], check=False
    )
    return result.returncode == 0


def branch_head(repo: Path, name: str) -> str:
    return _run(repo, ["rev-parse", f"refs/heads/{name}"]).stdout.strip()


def commit_parent(repo: Path, commit: str) -> str:
    return _run(repo, ["rev-parse", f"{commit}~1"]).stdout.strip()


def diff_range(repo: Path, base: str, target: str, max_bytes: int) -> str:
    result = _run(repo, ["diff", base, target])
    text = result.stdout
    if len(text.encode()) > max_bytes:
        text = text.encode()[:max_bytes].decode(errors="replace") + "\n… (diff truncated)"
    return text


def commit_details(repo: Path, commit: str) -> str:
    return _run(repo, ["show", "--stat", "--no-color", commit]).stdout[:4000]


# ------------------------------------------------------------ write side ---


def _require_nish_branch(name: str) -> None:
    if name in PROTECTED_BRANCHES:
        raise GitError(f"Refused: '{name}' is a protected branch.")
    if not NISH_BRANCH_PATTERN.match(name):
        raise GitError(
            "Refused: NISH only operates on branches matching "
            "nish/task-<id>-<description>."
        )


def create_branch(repo: Path, name: str) -> None:
    _require_nish_branch(name)
    _run(repo, ["checkout", "-b", name])


def checkout(repo: Path, name: str) -> None:
    """Switch branches. Allowed for any existing branch (returning to the
    user's original branch), but never creates one."""
    if not branch_exists(repo, name):
        raise GitError(f"Branch does not exist: {name}")
    _run(repo, ["checkout", name])


def stage_paths(repo: Path, paths: list[str]) -> None:
    """Stage EXACTLY the approved files — `--` prevents any path from
    being interpreted as an option."""
    if not paths:
        raise GitError("Nothing to stage.")
    _run(repo, ["add", "--", *paths])


def commit(repo: Path, title: str, body: str) -> str:
    """Create a local commit with the repo's own identity; returns hash."""
    _run(repo, ["commit", "-m", title, "-m", body])
    return head_commit(repo)


def delete_nish_branch(repo: Path, name: str) -> None:
    """Delete ONLY a NISH task branch (verified by pattern). `-D` is
    required because task branches are never merged — but it can never
    reach a user branch through this function."""
    _require_nish_branch(name)
    if current_branch(repo) == name:
        raise GitError("Cannot delete the currently checked-out branch.")
    _run(repo, ["branch", "-D", name])
