"""Tool permission system.

Every tool the agent can use is registered here with the capabilities it
requires. Every task carries an explicit set of granted capabilities.
Before any tool runs, the registry checks grant ⊇ requirement and logs
the decision — allowed or denied — to the audit log.

Key properties:

  * Deny by default: an unregistered tool cannot run at all.
  * Grants are per-task and immutable after creation (a frozenset), so
    an agent cannot escalate its own permissions mid-task.
  * In this part of the phase, tasks are only ever granted READ_REPO.
    WRITE_WORKSPACE / RUN_COMMANDS / GIT_WRITE exist in the enum so the
    model is complete, but nothing grants them yet.
"""

import enum
from dataclasses import dataclass, field

from app.core.audit import AuditLogger


class Capability(enum.StrEnum):
    """Things a tool might need to be allowed to do."""

    READ_REPO = "read_repo"              # read files inside the workspace
    WRITE_WORKSPACE = "write_workspace"  # modify files inside an isolated copy
    RUN_COMMANDS = "run_commands"        # run allowlisted commands
    INSTALL_PACKAGES = "install_packages"  # always requires user approval
    GIT_WRITE = "git_write"              # branch/commit (merge is user-only)
    NETWORK = "network"                  # any outbound network access


class PermissionDeniedError(Exception):
    """Raised when a tool call is attempted without the required grants."""

    def __init__(self, tool: str, missing: set[Capability]) -> None:
        self.tool = tool
        self.missing = missing
        names = ", ".join(sorted(capability.value for capability in missing))
        super().__init__(f"Tool '{tool}' denied: missing capability [{names}]")


@dataclass(frozen=True)
class ToolSpec:
    """A registered tool and what it needs."""

    name: str
    requires: frozenset[Capability]
    description: str = ""


@dataclass
class ToolRegistry:
    """Deny-by-default registry of tools and their required capabilities."""

    audit: AuditLogger
    _tools: dict[str, ToolSpec] = field(default_factory=dict)

    def register(
        self,
        name: str,
        requires: set[Capability],
        description: str = "",
    ) -> None:
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered.")
        self._tools[name] = ToolSpec(
            name=name, requires=frozenset(requires), description=description
        )

    def check(
        self,
        tool_name: str,
        granted: frozenset[Capability],
        task_id: str | None = None,
    ) -> None:
        """Raise PermissionDeniedError unless the grant covers the tool.

        Every decision — including denials — is written to the audit log,
        so attempted overreach is always visible.
        """
        spec = self._tools.get(tool_name)
        if spec is None:
            self.audit.record(
                actor="permissions",
                action="tool_check",
                outcome="denied",
                task_id=task_id,
                detail={"tool": tool_name, "reason": "tool not registered"},
            )
            raise PermissionDeniedError(tool_name, set(Capability))

        missing = set(spec.requires) - set(granted)
        if missing:
            self.audit.record(
                actor="permissions",
                action="tool_check",
                outcome="denied",
                task_id=task_id,
                detail={
                    "tool": tool_name,
                    "missing": sorted(capability.value for capability in missing),
                },
            )
            raise PermissionDeniedError(tool_name, missing)

        self.audit.record(
            actor="permissions",
            action="tool_check",
            outcome="ok",
            task_id=task_id,
            detail={"tool": tool_name},
        )


def build_default_registry(audit: AuditLogger) -> ToolRegistry:
    """Register the tools that exist in this part of the phase."""
    registry = ToolRegistry(audit=audit)
    registry.register(
        "repo.list_tree", {Capability.READ_REPO}, "List files in the workspace"
    )
    registry.register(
        "repo.read_file", {Capability.READ_REPO}, "Read one workspace file"
    )
    registry.register(
        "repo.search", {Capability.READ_REPO}, "Search workspace file contents"
    )
    return registry
