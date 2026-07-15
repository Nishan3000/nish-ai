"""Safe command execution for the coding agent.

The ONLY way NISH runs a command. Layers, in order:

  1. Policy gate — the command string must evaluate to ALLOWED under the
     strict allowlist in tools/command_policy.py. REQUIRES_APPROVAL
     commands (package installs, git writes) are also refused here:
     this milestone permits none of them. Shell metacharacters were
     already rejected by the policy, and we never use a shell anyway.
  2. Execution — subprocess.run with an ARGUMENT ARRAY (shell=False is
     the subprocess default and there is no shell string to interpret),
     a sanitized minimal environment (no API keys, no tokens — only
     PATH, HOME, LANG and a writable TMPDIR), the working directory
     pinned to the given root, and a hard timeout.
  3. Output handling — both streams truncated to a byte cap and passed
     through the audit redactor so a test that prints a credential
     doesn't propagate it.
  4. Audit — command, duration, exit code. Never full output.
"""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from app.core.audit import get_audit_logger, redact
from app.core.config import get_settings
from app.tools.command_policy import Decision, evaluate_command


class CommandRejected(Exception):
    """The policy refused this command."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class CommandResult:
    command: str
    exit_code: int | None
    duration_ms: int
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def passed(self) -> bool:
        return not self.timed_out and self.exit_code == 0


def _sanitized_env() -> dict[str, str]:
    """Minimal environment: tools can run, secrets cannot leak."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        # CI=1 makes most JS tooling non-interactive.
        "CI": "1",
    }
    return env


def _truncate(raw: bytes, limit: int) -> str:
    text = raw[:limit].decode("utf-8", errors="replace")
    if len(raw) > limit:
        text += f"\n… [output truncated at {limit} bytes]"
    return str(redact(text))


def run_allowlisted(
    command: str,
    cwd: Path,
    timeout_seconds: float | None = None,
) -> CommandResult:
    """Run one allowlisted command inside `cwd`. Raises CommandRejected
    for anything the policy does not explicitly ALLOW."""
    settings = get_settings()
    audit = get_audit_logger(settings.agent_audit_log_path)

    verdict = evaluate_command(command)
    if verdict.decision is not Decision.ALLOWED:
        audit.record(
            actor="coding_executor", action="run_command", outcome="denied",
            detail={"command": command[:200], "reason": verdict.reason},
        )
        raise CommandRejected(verdict.reason)

    return _execute(
        list(verdict.argv),
        command=command,
        cwd=cwd,
        timeout_seconds=timeout_seconds or settings.coding_command_timeout_seconds,
        max_output=settings.coding_max_output_bytes,
        audit=audit,
    )


def _execute(
    argv: list[str],
    *,
    command: str,
    cwd: Path,
    timeout_seconds: float,
    max_output: int,
    audit,
) -> CommandResult:
    """Execute an already-approved argv. Kept separate so the timeout and
    truncation machinery is unit-testable in isolation."""
    started = time.monotonic()
    timed_out = False
    exit_code: int | None = None
    stdout = stderr = ""
    try:
        completed = subprocess.run(  # noqa: S603 — argv array, no shell
            argv,
            cwd=str(cwd),
            env=_sanitized_env(),
            capture_output=True,
            timeout=timeout_seconds,
        )
        exit_code = completed.returncode
        stdout = _truncate(completed.stdout, max_output)
        stderr = _truncate(completed.stderr, max_output)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = _truncate(exc.stdout or b"", max_output)
        stderr = f"Command timed out after {timeout_seconds:.0f}s."
    except FileNotFoundError:
        exit_code = 127
        stderr = f"Command not found: {argv[0]}"

    duration_ms = int((time.monotonic() - started) * 1000)
    audit.record(
        actor="coding_executor", action="run_command",
        outcome="ok" if exit_code == 0 else "error",
        detail={
            "command": command[:200],
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "timed_out": timed_out,
        },
    )
    return CommandResult(
        command=command, exit_code=exit_code, duration_ms=duration_ms,
        stdout=stdout, stderr=stderr, timed_out=timed_out,
    )
