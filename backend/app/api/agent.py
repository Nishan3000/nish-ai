"""Agent API endpoints.

POST /api/agent/tasks         create a task and run the planner
GET  /api/agent/tasks         list tasks
GET  /api/agent/tasks/{id}    one task (state, plan, history)
GET  /api/agent/repo/tree     audited, guarded file listing
GET  /api/agent/repo/file     audited, guarded file read
GET  /api/agent/audit/verify  check the audit log's hash chain

Security note (deliberate, temporary): there is no authentication yet —
that is the PostgreSQL/accounts phase. Until then these endpoints must
only ever be bound to localhost, which is how the run instructions set
things up. The permission system below is about what the AGENT may do,
not about who the USER is.

Dependencies are built lazily (one shared instance per process) so tests
can point the workspace at a temp directory before first use.
"""

import logging
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.agents.models import (
    AgentTask,
    AuditVerifyResponse,
    RepoFileResponse,
    RepoTreeResponse,
    TaskCreateRequest,
    TaskListResponse,
    TaskState,
)
from app.agents.planner import PlannerAgent, PlanningError
from app.agents.state_machine import transition
from app.agents.task_store import TaskNotFoundError, TaskStore
from app.core.audit import AuditLogger
from app.core.config import get_settings
from app.services.ollama import OllamaService
from app.tools.path_guard import PathAccessError, PathGuard
from app.tools.permissions import (
    Capability,
    PermissionDeniedError,
    build_default_registry,
)
from app.tools.repo_reader import RepoReader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentContext:
    """All agent infrastructure, wired once per process."""

    def __init__(self) -> None:
        settings = get_settings()
        workspace = Path(settings.agent_workspace_root)
        workspace.mkdir(parents=True, exist_ok=True)

        self.settings = settings
        self.audit = AuditLogger(settings.agent_audit_log_path)
        self.guard = PathGuard(workspace)
        self.registry = build_default_registry(self.audit)
        self.reader = RepoReader(
            self.guard,
            self.registry,
            self.audit,
            max_read_bytes=settings.agent_max_read_bytes,
            max_tree_entries=settings.agent_max_tree_entries,
        )
        self.planner = PlannerAgent(
            OllamaService(settings), self.reader, self.audit, settings
        )
        self.tasks = TaskStore()


@lru_cache
def get_context() -> AgentContext:
    """Shared per-process context; tests call get_context.cache_clear()."""
    return AgentContext()


# ------------------------------------------------------------------ tasks --


@router.post("/tasks", response_model=AgentTask, status_code=201)
async def create_task(request: TaskCreateRequest) -> AgentTask:
    """Create a task and produce its plan (PENDING → PLANNING → PLANNED)."""
    context = get_context()
    task = AgentTask(description=request.description)
    context.tasks.add(task)
    context.audit.record(
        actor="api",
        action="task_created",
        outcome="ok",
        task_id=task.id,
        detail={"description": request.description[:500]},
    )

    transition(task, TaskState.PLANNING, context.audit)
    try:
        task.plan = await context.planner.plan(
            task.id, task.description, task.granted_capabilities
        )
    except PlanningError as exc:
        task.error = str(exc)
        transition(task, TaskState.FAILED, context.audit, note=str(exc)[:200])
        # 502: the failure is between us and the model, not the client.
        raise HTTPException(status_code=502, detail=str(exc))
    except PermissionDeniedError as exc:
        task.error = str(exc)
        transition(task, TaskState.FAILED, context.audit, note=str(exc)[:200])
        raise HTTPException(status_code=403, detail=str(exc))

    transition(task, TaskState.PLANNED, context.audit)
    return task


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks() -> TaskListResponse:
    return TaskListResponse(tasks=get_context().tasks.list())


@router.get("/tasks/{task_id}", response_model=AgentTask)
async def get_task(task_id: str) -> AgentTask:
    try:
        return get_context().tasks.get(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ------------------------------------------------------------------- repo --


@router.get("/repo/tree", response_model=RepoTreeResponse)
async def repo_tree() -> RepoTreeResponse:
    """Guarded listing of the agent workspace (what the planner sees)."""
    context = get_context()
    # Direct inspection by the user gets a fresh read-only grant.
    entries = context.reader.list_tree(frozenset({Capability.READ_REPO}))
    return RepoTreeResponse(
        root=str(context.guard.root),
        entries=[
            {"path": entry.path, "size_bytes": entry.size_bytes}
            for entry in entries
        ],
    )


@router.get("/repo/file", response_model=RepoFileResponse)
async def repo_file(path: str = Query(min_length=1, max_length=500)) -> RepoFileResponse:
    """Guarded read of one workspace file."""
    context = get_context()
    try:
        result = context.reader.read_file(
            path, frozenset({Capability.READ_REPO})
        )
    except PathAccessError as exc:
        raise HTTPException(status_code=403, detail=exc.reason)
    return RepoFileResponse(
        path=result.path, content=result.content, truncated=result.truncated
    )


# ------------------------------------------------------------------ audit --


@router.get("/audit/verify", response_model=AuditVerifyResponse)
async def audit_verify() -> AuditVerifyResponse:
    """Verify the audit log's hash chain end to end."""
    ok, message = get_context().audit.verify_chain()
    return AuditVerifyResponse(ok=ok, message=message)
