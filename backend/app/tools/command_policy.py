"""Command allowlist policy.

This module DECIDES whether a command may run; it does not run anything.
The executor arrives in the next part of the phase, together with the
test agent — separating policy from execution means the policy can be
tested exhaustively on its own, and the executor will be a thin wrapper
that refuses to start unless the policy said ALLOWED.

Decision model (fail-closed):

  * ALLOWED            — on the allowlist with acceptable arguments.
  * REQUIRES_APPROVAL  — legitimate but sensitive (package installs,
                         git writes); the user must approve explicitly.
  * BLOCKED            — everything else. Unknown == blocked.

Hard rules, in evaluation order:
  1. The raw string may not contain shell metacharacters. Commands will
     be executed WITHOUT a shell (subprocess with a list argv), so
     `;`, `|`, `&&`, backticks, `$(...)`, redirects etc. are rejected
     outright rather than interpreted.
  2. The executable must be on the allowlist below.
  3. Per-executable argument rules apply (e.g. git is limited to
     read-only subcommands; `python` may only run `-m pytest` etc.).
  4. Environment-exposing and destructive commands are explicitly
     blocked with a clear reason, so the audit log shows intent.
"""

import enum
import shlex
from dataclasses import dataclass

# Characters that only make sense when a shell interprets the string.
_SHELL_METACHARACTERS = set(";|&<>`$(){}[]*?~#\\\n\r")

# Executables that are never acceptable, with human-readable reasons.
_BLOCKED_EXECUTABLES: dict[str, str] = {
    "rm": "destructive: deletes files",
    "rmdir": "destructive: deletes directories",
    "dd": "destructive: raw disk writes",
    "mkfs": "destructive: formats filesystems",
    "shred": "destructive: destroys file contents",
    "chmod": "changes permissions",
    "chown": "changes ownership",
    "sudo": "privilege escalation",
    "su": "privilege escalation",
    "env": "exposes environment variables",
    "printenv": "exposes environment variables",
    "export": "modifies environment",
    "set": "may expose environment",
    "curl": "network access",
    "wget": "network access",
    "nc": "network access",
    "ssh": "network access",
    "scp": "network access",
    "bash": "arbitrary shell execution",
    "sh": "arbitrary shell execution",
    "zsh": "arbitrary shell execution",
    "powershell": "arbitrary shell execution",
    "cmd": "arbitrary shell execution",
    "eval": "arbitrary code execution",
    "exec": "arbitrary code execution",
    "kill": "process control",
    "pkill": "process control",
    "shutdown": "system control",
    "reboot": "system control",
}

# git subcommands the agent may run freely (all read-only).
_GIT_READ_ONLY: frozenset[str] = frozenset(
    {"status", "diff", "log", "show", "ls-files", "blame", "rev-parse"}
)
# git subcommands that exist for later parts but always need approval.
_GIT_APPROVAL: frozenset[str] = frozenset(
    {"add", "commit", "branch", "checkout", "switch", "stash", "restore"}
)
# git subcommands that are never run by the agent (user-only actions).
_GIT_BLOCKED: dict[str, str] = {
    "merge": "merging is a user-only action",
    "push": "publishing is a user-only action",
    "pull": "network access",
    "fetch": "network access",
    "clone": "network access",
    "reset": "can destroy history",
    "clean": "destructive: deletes untracked files",
    "rebase": "rewrites history",
    "filter-branch": "rewrites history",
    "config": "can change credentials/hooks",
    "remote": "can change where code is sent",
}

# python -m modules the agent may invoke.
_PYTHON_MODULES_ALLOWED: frozenset[str] = frozenset(
    {"pytest", "ruff", "black", "mypy", "unittest"}
)


class Decision(enum.StrEnum):
    ALLOWED = "allowed"
    REQUIRES_APPROVAL = "requires_approval"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class PolicyResult:
    """Outcome of evaluating one command string."""

    decision: Decision
    reason: str
    argv: tuple[str, ...] = ()   # parsed argv, only present when not BLOCKED


def evaluate_command(raw_command: str) -> PolicyResult:
    """Evaluate a command string against the allowlist policy."""
    stripped = raw_command.strip()
    if not stripped:
        return PolicyResult(Decision.BLOCKED, "empty command")

    # Rule 1: no shell metacharacters, ever.
    bad_characters = sorted(set(stripped) & _SHELL_METACHARACTERS)
    if bad_characters:
        return PolicyResult(
            Decision.BLOCKED,
            f"shell metacharacters not permitted: {' '.join(bad_characters)}",
        )

    try:
        argv = tuple(shlex.split(stripped))
    except ValueError as exc:
        return PolicyResult(Decision.BLOCKED, f"unparseable command: {exc}")
    if not argv:
        return PolicyResult(Decision.BLOCKED, "empty command")

    executable = argv[0].lower()
    # Strip a path prefix like /usr/bin/rm — judge the basename.
    executable = executable.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

    # Rule 4 (checked early for clearer audit reasons).
    if executable in _BLOCKED_EXECUTABLES:
        return PolicyResult(
            Decision.BLOCKED, f"'{executable}' blocked: {_BLOCKED_EXECUTABLES[executable]}"
        )

    # Rule 2 + 3: per-executable rules.
    if executable in {"pytest", "ruff", "black", "mypy"}:
        return PolicyResult(Decision.ALLOWED, f"'{executable}' is allowlisted", argv)

    if executable in {"python", "python3"}:
        if len(argv) >= 3 and argv[1] == "-m" and argv[2] in _PYTHON_MODULES_ALLOWED:
            return PolicyResult(
                Decision.ALLOWED, f"python -m {argv[2]} is allowlisted", argv
            )
        return PolicyResult(
            Decision.BLOCKED,
            "python may only run allowlisted modules "
            f"(-m {'/'.join(sorted(_PYTHON_MODULES_ALLOWED))})",
        )

    if executable in {"pip", "pip3"}:
        if len(argv) >= 2 and argv[1] == "install":
            return PolicyResult(
                Decision.REQUIRES_APPROVAL,
                "package installation requires user approval",
                argv,
            )
        return PolicyResult(Decision.BLOCKED, "only 'pip install' is recognised")

    if executable == "npm":
        if len(argv) >= 2 and argv[1] == "test":
            return PolicyResult(Decision.ALLOWED, "npm test is allowlisted", argv)
        if len(argv) >= 3 and argv[1] == "run" and argv[2] in {
            "lint", "build", "typecheck", "test",
        }:
            # npm run is restricted to KNOWN script names: an arbitrary
            # script name would be arbitrary code execution by proxy.
            return PolicyResult(
                Decision.ALLOWED, f"npm run {argv[2]} is allowlisted", argv
            )
        if len(argv) == 2 and argv[1] == "run":
            return PolicyResult(Decision.BLOCKED, "npm run needs an allowlisted script")
        if len(argv) >= 2 and argv[1] in {"install", "ci"}:
            return PolicyResult(
                Decision.REQUIRES_APPROVAL,
                "package installation requires user approval",
                argv,
            )
        return PolicyResult(Decision.BLOCKED, "npm subcommand not allowlisted")

    if executable == "npx":
        # Exactly one npx invocation is recognised: the TypeScript
        # no-emit check. Anything else via npx is arbitrary execution.
        if list(argv[1:]) == ["tsc", "--noEmit"]:
            return PolicyResult(Decision.ALLOWED, "npx tsc --noEmit is allowlisted", argv)
        return PolicyResult(Decision.BLOCKED, "only 'npx tsc --noEmit' is permitted")

    if executable == "git":
        if len(argv) < 2:
            return PolicyResult(Decision.BLOCKED, "bare 'git' is not a command")
        subcommand = argv[1].lower()
        if subcommand in _GIT_BLOCKED:
            return PolicyResult(
                Decision.BLOCKED, f"git {subcommand}: {_GIT_BLOCKED[subcommand]}"
            )
        if subcommand in _GIT_READ_ONLY:
            return PolicyResult(
                Decision.ALLOWED, f"git {subcommand} is read-only", argv
            )
        if subcommand in _GIT_APPROVAL:
            return PolicyResult(
                Decision.REQUIRES_APPROVAL,
                f"git {subcommand} requires user approval",
                argv,
            )
        return PolicyResult(Decision.BLOCKED, f"git {subcommand} is not recognised")

    # Rule 2 default: unknown executables are blocked.
    return PolicyResult(Decision.BLOCKED, f"'{executable}' is not on the allowlist")
