"""State machine for coding tasks — same single-table-of-truth pattern
as the v0.3 agent pipeline, operating on the ORM CodingTask. The only
edge into 'approved' or 'rejected' starts at 'awaiting_approval', so a
decision without a completed review is structurally impossible."""

from app.core.audit import get_audit_logger
from app.core.config import get_settings
from app.database.models import CodingTask

STATES = (
    "created", "planning", "planned", "workspace_ready", "generating",
    "generated", "validating", "validated", "awaiting_approval",
    "approved", "rejected", "failed",
)

TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"planning", "failed"}),
    "planning": frozenset({"planned", "failed"}),
    "planned": frozenset({"workspace_ready", "failed"}),
    "workspace_ready": frozenset({"generating", "failed"}),
    "generating": frozenset({"generated", "failed"}),
    "generated": frozenset({"validating", "awaiting_approval", "failed"}),
    "validating": frozenset({"validated", "failed"}),
    "validated": frozenset({"awaiting_approval", "validating", "failed"}),
    "awaiting_approval": frozenset({"approved", "rejected"}),
    "approved": frozenset(),
    "rejected": frozenset(),
    "failed": frozenset(),
}


class IllegalCodingTransition(Exception):
    def __init__(self, from_state: str, to_state: str) -> None:
        super().__init__(f"Illegal transition: {from_state} -> {to_state}")


def transition(task: CodingTask, to_state: str, note: str = "") -> None:
    audit = get_audit_logger(get_settings().agent_audit_log_path)
    allowed = TRANSITIONS.get(task.state, frozenset())
    if to_state not in allowed:
        audit.record(
            actor="coding_state", action="transition", outcome="denied",
            task_id=str(task.id),
            detail={"from": task.state, "to": to_state},
        )
        raise IllegalCodingTransition(task.state, to_state)
    audit.record(
        actor="coding_state", action="transition", outcome="ok",
        task_id=str(task.id),
        detail={"from": task.state, "to": to_state, "note": note[:150]},
    )
    task.state = to_state
