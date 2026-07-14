"""Task-state models for the agent pipeline.

An AgentTask moves through a fixed set of states (see `TaskState`); the
allowed transitions live in `state_machine.py`. The full target pipeline
is modelled now, even though this part of the phase only ever reaches
PLANNED — later parts fill in the remaining states without changing the
model.

Everything is Pydantic so the API can return tasks directly and the
structures are validated at every boundary.
"""

import enum
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.tools.permissions import Capability


class TaskState(enum.StrEnum):
    """Lifecycle of an agent task — mirrors the target workflow."""

    PENDING = "pending"                    # created, nothing has run
    PLANNING = "planning"                  # planner is working
    PLANNED = "planned"                    # plan ready (terminal for now)
    INSPECTING = "inspecting"              # reading the repository
    WORKSPACE_READY = "workspace_ready"    # isolated copy created
    MODIFYING = "modifying"                # coding agent editing files
    TESTING = "testing"                    # running lint/format/tests
    REVIEWING = "reviewing"                # reviewer agent
    SECURITY_REVIEW = "security_review"    # security agent
    AWAITING_APPROVAL = "awaiting_approval"  # diff shown, user decides
    MERGING = "merging"                    # user approved; applying
    COMPLETED = "completed"                # done
    REJECTED = "rejected"                  # user said no
    FAILED = "failed"                      # unrecoverable error
    CANCELLED = "cancelled"                # user cancelled


class StepKind(enum.StrEnum):
    """What a plan step intends to do (drives later permission checks)."""

    INSPECT = "inspect"
    MODIFY = "modify"
    TEST = "test"
    REVIEW = "review"


class PlanStep(BaseModel):
    """One step in the planner's structured output."""

    id: int = Field(ge=1)
    title: str = Field(min_length=3, max_length=200)
    kind: StepKind
    description: str = Field(min_length=3, max_length=2_000)
    target_files: list[str] = Field(default_factory=list, max_length=30)


class Plan(BaseModel):
    """The planner's full structured output."""

    goal: str = Field(min_length=3, max_length=1_000)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    risks: list[str] = Field(default_factory=list, max_length=20)
    steps: list[PlanStep] = Field(min_length=1, max_length=25)


class TransitionRecord(BaseModel):
    """One recorded state change, kept on the task for traceability."""

    from_state: TaskState
    to_state: TaskState
    at: datetime
    note: str = ""


class AgentTask(BaseModel):
    """A single agent task and everything known about it."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = Field(min_length=5, max_length=4_000)
    state: TaskState = TaskState.PENDING
    # Immutable capability grant — set at creation, never widened.
    # This part of the phase only ever grants READ_REPO.
    granted_capabilities: frozenset[Capability] = frozenset(
        {Capability.READ_REPO}
    )
    plan: Plan | None = None
    error: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    history: list[TransitionRecord] = Field(default_factory=list)

    model_config = {"frozen": False}


class TaskCreateRequest(BaseModel):
    """Body of POST /api/agent/tasks."""

    description: str = Field(min_length=5, max_length=4_000)


class TaskListResponse(BaseModel):
    """Body of GET /api/agent/tasks."""

    tasks: list[AgentTask]


class AuditVerifyResponse(BaseModel):
    """Body of GET /api/agent/audit/verify."""

    ok: bool
    message: str


class RepoTreeResponse(BaseModel):
    """Body of GET /api/agent/repo/tree."""

    root: str
    entries: list[dict[str, int | str]]


class RepoFileResponse(BaseModel):
    """Body of GET /api/agent/repo/file."""

    path: str
    content: str
    truncated: bool


class ErrorDetail(BaseModel):
    """Uniform error shape used in OpenAPI docs."""

    detail: str


# Convenience alias used by the API layer.
TaskStateLiteral = Literal[
    "pending", "planning", "planned", "failed"
]  # states reachable in this part of the phase
