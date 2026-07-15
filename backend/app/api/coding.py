"""Coding-agent API — the controlled pipeline, one endpoint per stage.

Projects:
  POST   /api/coding/projects              register (path validated)
  GET    /api/coding/projects              list
  DELETE /api/coding/projects/{id}         unregister (files untouched)
  POST   /api/coding/projects/{id}/scan    inspect + technologies
  GET    /api/coding/projects/{id}/file    guarded single-file read
  GET    /api/coding/projects/{id}/search  filename/content search

Tasks (each stage is an explicit user action — nothing runs unbidden):
  POST /api/coding/tasks                       create + plan
  GET  /api/coding/tasks?project_id=           list
  GET  /api/coding/tasks/{id}                  full detail
  POST /api/coding/tasks/{id}/workspace        isolated copy
  POST /api/coding/tasks/{id}/generate         model writes proposal
  POST /api/coding/tasks/{id}/validate         run allowlisted commands
  POST /api/coding/tasks/{id}/review           deterministic review
  POST /api/coding/tasks/{id}/decision         approve/reject (records
        the decision ONLY — applying to the live repo is a later
        milestone, and the response says so explicitly)
  DELETE /api/coding/tasks/{id}/workspace      cleanup

Everything is ownership-checked; foreign projects/tasks 404.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.conversations import current_user
from app.coding import inspect as inspect_service
from app.coding import state as task_state
from app.coding.executor import CommandRejected, run_allowlisted
from app.coding.generator import generate_proposal
from app.coding.paths import ProjectPathError, make_guard, validate_project_root
from app.coding.planner import CodingPlan, CodingPlanner, CodingPlanningError
from app.coding.review import review_proposal
from app.coding.workspace import cleanup_workspace, create_workspace
from app.core.audit import get_audit_logger
from app.core.config import get_settings
from app.database.models import (
    Approval,
    CodingProposal,
    CodingProposalFile,
    CodingTask,
    RegisteredProject,
    User,
    ValidationRun,
)
from app.database.session import get_db
from app.schemas.coding import (
    DecisionOut,
    DecisionRequest,
    ProjectOut,
    ProjectRegister,
    ProposalFileOut,
    ProposalOut,
    ReviewOut,
    ScanOut,
    TaskCreate,
    TaskOut,
    ValidateRequest,
    ValidationRunOut,
)
from app.services.secret_scan import detect_secret
from app.tools.path_guard import PathAccessError

router = APIRouter(prefix="/coding", tags=["coding"])


def _audit():
    return get_audit_logger(get_settings().agent_audit_log_path)


def _owned_project(
    db: Session, user: User, project_id: uuid.UUID
) -> RegisteredProject:
    project = db.scalar(
        select(RegisteredProject).where(
            RegisteredProject.id == project_id,
            RegisteredProject.user_id == user.id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


def _owned_task(db: Session, user: User, task_id: uuid.UUID) -> CodingTask:
    task = db.scalar(
        select(CodingTask).where(
            CodingTask.id == task_id, CodingTask.user_id == user.id
        )
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


def _project_guard(project: RegisteredProject):
    try:
        root = validate_project_root(project.root_path)
    except ProjectPathError as exc:
        # The directory changed since registration (moved/deleted).
        raise HTTPException(
            status_code=409, detail=f"Project path invalid: {exc.reason}"
        )
    return make_guard(root)


# --------------------------------------------------------------- projects --


@router.post("/projects", response_model=ProjectOut, status_code=201)
def register_project(
    body: ProjectRegister,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RegisteredProject:
    try:
        resolved = validate_project_root(body.root_path)
    except ProjectPathError as exc:
        _audit().record(
            actor="coding_projects", action="register", outcome="denied",
            detail={"reason": exc.reason},
        )
        raise HTTPException(status_code=422, detail=exc.reason)

    existing = db.scalar(
        select(RegisteredProject).where(
            RegisteredProject.user_id == user.id,
            RegisteredProject.root_path == str(resolved),
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="This path is already registered."
        )

    project = RegisteredProject(
        user_id=user.id,
        name=body.name,
        root_path=str(resolved),
        description=body.description,
        default_branch=body.default_branch,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    _audit().record(
        actor="coding_projects", action="register", outcome="ok",
        detail={"project_id": str(project.id), "name": project.name},
    )
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[RegisteredProject]:
    return list(
        db.scalars(
            select(RegisteredProject)
            .where(RegisteredProject.user_id == user.id)
            .order_by(RegisteredProject.created_at.desc())
        ).all()
    )


@router.delete("/projects/{project_id}", status_code=204)
def unregister_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    project = _owned_project(db, user, project_id)
    db.delete(project)  # registration record only — files are untouched
    db.commit()
    _audit().record(
        actor="coding_projects", action="unregister", outcome="ok",
        detail={"project_id": str(project_id)},
    )


@router.post("/projects/{project_id}/scan", response_model=ScanOut)
def scan_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ScanOut:
    from sqlalchemy import func as sa_func

    project = _owned_project(db, user, project_id)
    guard = _project_guard(project)
    try:
        inspection = inspect_service.inspect_project(guard)
    except ProjectPathError as exc:
        raise HTTPException(status_code=413, detail=exc.reason)
    project.last_scanned_at = sa_func.now()
    db.commit()
    return ScanOut(
        files=inspection.files,
        technologies=inspection.technologies,
        readme_excerpt=inspection.readme_excerpt,
        dependency_files=sorted(inspection.dependency_excerpts.keys()),
        test_commands=inspection.test_commands,
        git_branch=inspection.git_branch,
        git_dirty_files=inspection.git_dirty_files,
    )


@router.get("/projects/{project_id}/file")
def read_project_file(
    project_id: uuid.UUID,
    path: str = Query(min_length=1, max_length=500),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    project = _owned_project(db, user, project_id)
    guard = _project_guard(project)
    try:
        content, truncated = inspect_service.read_file(guard, path)
    except PathAccessError as exc:
        raise HTTPException(status_code=403, detail=exc.reason)
    return {"path": path, "content": content, "truncated": truncated}


@router.get("/projects/{project_id}/search")
def search_project(
    project_id: uuid.UUID,
    q: str = Query(min_length=2, max_length=120),
    kind: str = Query(default="content", pattern="^(content|filename)$"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    project = _owned_project(db, user, project_id)
    guard = _project_guard(project)
    hits = inspect_service.search(guard, q, in_names=(kind == "filename"))
    return {"hits": hits}


# ------------------------------------------------------------------ tasks --


@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(
    body: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TaskOut:
    project = _owned_project(db, user, body.project_id)
    guard = _project_guard(project)

    task = CodingTask(
        user_id=user.id, project_id=project.id, description=body.description
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    task_state.transition(task, "planning")
    db.commit()
    try:
        inspection = inspect_service.inspect_project(guard)
        plan, warnings = await CodingPlanner().plan(
            str(task.id), body.description, inspection
        )
    except (CodingPlanningError, ProjectPathError) as exc:
        task.error = str(exc)
        task_state.transition(task, "failed", note=str(exc)[:150])
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc))

    plan_payload = plan.model_dump()
    if warnings:
        plan_payload["risks"] = [*plan.risks, *warnings]
    task.plan = plan_payload
    task_state.transition(task, "planned")
    db.commit()
    return _task_out(db, task)


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    project_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[TaskOut]:
    statement = (
        select(CodingTask)
        .where(CodingTask.user_id == user.id)
        .order_by(CodingTask.created_at.desc())
        .limit(20)
    )
    if project_id:
        statement = statement.where(CodingTask.project_id == project_id)
    return [_task_out(db, task) for task in db.scalars(statement).all()]


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TaskOut:
    return _task_out(db, _owned_task(db, user, task_id))


@router.post("/tasks/{task_id}/workspace", response_model=TaskOut)
def make_workspace(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TaskOut:
    task = _owned_task(db, user, task_id)
    project = _owned_project(db, user, task.project_id)
    guard = _project_guard(project)
    workspace = create_workspace(guard, task.id)
    task.workspace_path = str(workspace)
    task_state.transition(task, "workspace_ready")
    db.commit()
    return _task_out(db, task)


@router.post("/tasks/{task_id}/generate", response_model=TaskOut)
async def generate(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TaskOut:
    task = _owned_task(db, user, task_id)
    if task.plan is None or task.workspace_path is None:
        raise HTTPException(
            status_code=409,
            detail="Task needs a plan and a workspace before generation.",
        )
    plan = CodingPlan.model_validate(task.plan)
    task_state.transition(task, "generating")
    db.commit()

    result = await generate_proposal(
        task_id=str(task.id),
        task_description=task.description,
        plan_summary=plan.task_summary,
        steps=plan.steps,
        files_to_modify=plan.files_to_modify,
        files_to_create=plan.files_to_create,
        workspace=Path(task.workspace_path),
    )
    if not result.files:
        task.error = "No valid file changes could be generated. " + \
            "; ".join(result.warnings)[:500]
        task_state.transition(task, "failed", note="empty proposal")
        db.commit()
        raise HTTPException(status_code=502, detail=task.error)

    proposal = CodingProposal(
        task_id=task.id,
        summary=plan.task_summary,
        diff=result.diff,
        warnings=result.warnings,
    )
    db.add(proposal)
    db.flush()
    for item in result.files:
        db.add(
            CodingProposalFile(
                proposal_id=proposal.id,
                path=item.path,
                change_type=item.change_type,
                original_content=item.original_content,
                new_content=item.new_content,
            )
        )
    task_state.transition(task, "generated")
    db.commit()
    return _task_out(db, task)


@router.post("/tasks/{task_id}/validate", response_model=TaskOut)
def validate(
    task_id: uuid.UUID,
    body: ValidateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TaskOut:
    task = _owned_task(db, user, task_id)
    if task.workspace_path is None:
        raise HTTPException(status_code=409, detail="Task has no workspace.")
    if task.state in {"generated", "validated"}:
        task_state.transition(task, "validating")
        db.commit()
    elif task.state != "validating":
        raise HTTPException(
            status_code=409, detail=f"Cannot validate from state '{task.state}'."
        )

    for command in body.commands:
        try:
            result = run_allowlisted(command, cwd=Path(task.workspace_path))
        except CommandRejected as exc:
            db.add(
                ValidationRun(
                    task_id=task.id, command=command[:300], exit_code=None,
                    duration_ms=0, passed=False, timed_out=False,
                    output_excerpt=f"REFUSED by policy: {exc.reason}",
                )
            )
            continue
        excerpt = (result.stdout + "\n" + result.stderr).strip()[:4_000]
        db.add(
            ValidationRun(
                task_id=task.id, command=command[:300],
                exit_code=result.exit_code, duration_ms=result.duration_ms,
                passed=result.passed, timed_out=result.timed_out,
                output_excerpt=excerpt,
            )
        )
    task_state.transition(task, "validated")
    db.commit()
    return _task_out(db, task)


@router.post("/tasks/{task_id}/review", response_model=TaskOut)
def review(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TaskOut:
    task = _owned_task(db, user, task_id)
    if task.state not in {"generated", "validated"}:
        raise HTTPException(
            status_code=409, detail=f"Cannot review from state '{task.state}'."
        )
    task_state.transition(task, "awaiting_approval")
    db.commit()
    return _task_out(db, task)


@router.post("/tasks/{task_id}/decision", response_model=DecisionOut)
def decide(
    task_id: uuid.UUID,
    body: DecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> DecisionOut:
    task = _owned_task(db, user, task_id)
    if task.state != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail="Task is not awaiting approval — run the review first.",
        )
    proposal = db.scalar(
        select(CodingProposal)
        .where(CodingProposal.task_id == task.id)
        .order_by(CodingProposal.created_at.desc())
    )
    if proposal is None:
        raise HTTPException(status_code=409, detail="Task has no proposal.")

    db.add(
        Approval(
            proposal_id=proposal.id, decision=body.decision, note=body.note
        )
    )
    proposal.status = body.decision
    task_state.transition(task, body.decision, note=body.note[:100])
    db.commit()
    _audit().record(
        actor="coding_decision", action=body.decision, outcome="ok",
        task_id=str(task.id),
        detail={"proposal_id": str(proposal.id), "note": body.note[:150]},
    )
    if body.decision == "approved":
        message = (
            "Proposal approved and recorded. Note: applying approved changes "
            "to the live repository is NOT part of this milestone — the "
            "original project has not been modified."
        )
    else:
        message = "Proposal rejected and recorded. The original project was never modified."
    return DecisionOut(decision=body.decision, message=message)


@router.delete("/tasks/{task_id}/workspace", status_code=204)
def remove_workspace(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    task = _owned_task(db, user, task_id)
    cleanup_workspace(task.id)
    task.workspace_path = None
    db.commit()


# ---------------------------------------------------------------- helpers --


def _task_out(db: Session, task: CodingTask) -> TaskOut:
    proposal = db.scalar(
        select(CodingProposal)
        .where(CodingProposal.task_id == task.id)
        .order_by(CodingProposal.created_at.desc())
    )
    proposal_out = None
    review_out = None
    validation_rows = db.scalars(
        select(ValidationRun)
        .where(ValidationRun.task_id == task.id)
        .order_by(ValidationRun.id)
    ).all()
    validations = [ValidationRunOut.model_validate(row) for row in validation_rows]

    if proposal is not None:
        files = db.scalars(
            select(CodingProposalFile).where(
                CodingProposalFile.proposal_id == proposal.id
            )
        ).all()
        # Diffs shown to the user pass through secret redaction as a
        # last line of defence (contents were already scanned).
        from app.core.audit import redact

        proposal_out = ProposalOut(
            id=proposal.id,
            status=proposal.status,
            summary=proposal.summary,
            diff=str(redact(proposal.diff)),
            files=[ProposalFileOut.model_validate(item) for item in files],
            warnings=list(proposal.warnings or []),
            created_at=proposal.created_at,
        )
        from app.coding.generator import ProposedFile

        review_result = review_proposal(
            [
                ProposedFile(
                    path=item.path,
                    change_type=item.change_type,
                    original_content=item.original_content,
                    new_content=item.new_content,
                )
                for item in files
            ],
            [run.model_dump() for run in validations],
            list(proposal.warnings or []),
        )
        review_out = ReviewOut(
            findings=[f.__dict__ for f in review_result.findings],
            notes=review_result.notes,
            tests_ran=review_result.tests_ran,
            tests_passed=review_result.tests_passed,
            ready_for_approval=review_result.ready_for_approval,
        )

    plan = CodingPlan.model_validate(task.plan) if task.plan else None
    return TaskOut(
        id=task.id,
        project_id=task.project_id,
        description=task.description,
        state=task.state,
        plan=plan,
        error=task.error,
        created_at=task.created_at,
        proposal=proposal_out,
        validation_runs=validations,
        review=review_out,
    )
