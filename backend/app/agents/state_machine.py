"""Task state machine.

One table (`ALLOWED_TRANSITIONS`) is the single source of truth for how
a task may move between states. `transition()` is the ONLY function that
changes a task's state: it validates the move, appends to the task's
history, and writes an audit record — so an illegal jump (say, straight
to MERGING without approval) is structurally impossible rather than
merely discouraged.
"""

from datetime import datetime, timezone

from app.agents.models import AgentTask, TaskState, TransitionRecord
from app.core.audit import AuditLogger

# from-state -> set of legal to-states. Anything not listed is illegal.
ALLOWED_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.PENDING: frozenset({TaskState.PLANNING, TaskState.CANCELLED}),
    TaskState.PLANNING: frozenset(
        {TaskState.PLANNED, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.PLANNED: frozenset(
        {TaskState.INSPECTING, TaskState.CANCELLED}
    ),
    TaskState.INSPECTING: frozenset(
        {TaskState.WORKSPACE_READY, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.WORKSPACE_READY: frozenset(
        {TaskState.MODIFYING, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.MODIFYING: frozenset(
        {TaskState.TESTING, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.TESTING: frozenset(
        # tests fail -> back to MODIFYING for a bounded retry loop
        {TaskState.REVIEWING, TaskState.MODIFYING, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.REVIEWING: frozenset(
        {TaskState.SECURITY_REVIEW, TaskState.MODIFYING, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.SECURITY_REVIEW: frozenset(
        {TaskState.AWAITING_APPROVAL, TaskState.MODIFYING, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.AWAITING_APPROVAL: frozenset(
        # The ONLY way into MERGING is through AWAITING_APPROVAL —
        # i.e. through an explicit user decision.
        {TaskState.MERGING, TaskState.REJECTED, TaskState.CANCELLED}
    ),
    TaskState.MERGING: frozenset({TaskState.COMPLETED, TaskState.FAILED}),
    # Terminal states: no exits.
    TaskState.COMPLETED: frozenset(),
    TaskState.REJECTED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


class IllegalTransitionError(Exception):
    """Raised on any attempt to move a task along an unlisted edge."""

    def __init__(self, from_state: TaskState, to_state: TaskState) -> None:
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Illegal transition: {from_state.value} -> {to_state.value}"
        )


def transition(
    task: AgentTask,
    to_state: TaskState,
    audit: AuditLogger,
    note: str = "",
) -> AgentTask:
    """Move a task to a new state, or raise IllegalTransitionError.

    Every transition — legal or attempted-illegal — is audited.
    """
    allowed = ALLOWED_TRANSITIONS.get(task.state, frozenset())
    if to_state not in allowed:
        audit.record(
            actor="state_machine",
            action="state_transition",
            outcome="denied",
            task_id=task.id,
            detail={"from": task.state.value, "to": to_state.value},
        )
        raise IllegalTransitionError(task.state, to_state)

    record = TransitionRecord(
        from_state=task.state,
        to_state=to_state,
        at=datetime.now(timezone.utc),
        note=note,
    )
    task.history.append(record)
    task.state = to_state
    audit.record(
        actor="state_machine",
        action="state_transition",
        outcome="ok",
        task_id=task.id,
        detail={"from": record.from_state.value, "to": to_state.value, "note": note},
    )
    return task
