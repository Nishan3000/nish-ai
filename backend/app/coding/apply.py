"""Reviewed change application.

Applies an explicitly approved proposal to the REAL repository — but
only ever on a freshly created NISH feature branch, only after the
proposal's integrity hash matches the one recorded at approval time,
only onto a clean repository, and only committing after the approved
validation commands pass again on the branch. Any failure restores the
repository to exactly its pre-application state (original file contents
written back, created files removed, original branch checked out, task
branch deleted) — never leaving the user's repository dirty.

Nothing here can push, pull, merge, deploy, or touch remotes: those
verbs do not exist in gitops and are blocklisted as a backstop.
"""

import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coding import gitops
from app.coding.executor import CommandRejected, run_allowlisted
from app.coding.generator import PatchValidationError, validate_target
from app.coding.paths import validate_project_root
from app.coding.review import _DANGEROUS_PATTERNS
from app.core.audit import get_audit_logger
from app.core.config import get_settings
from app.database.models import (
    Approval,
    ChangeApplication,
    CodingProposal,
    CodingProposalFile,
    CodingTask,
    RegisteredProject,
    User,
    ValidationRun,
)
from app.services.secret_scan import detect_secret
from app.tools.path_guard import PathGuard


def _audit():
    return get_audit_logger(get_settings().agent_audit_log_path)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------- integrity ---


def compute_proposal_hash(
    proposal: CodingProposal, files: list[CodingProposalFile]
) -> str:
    """sha256 over the canonical proposal content. Any change to any
    file's path, kind, original snapshot, or proposed content — or to
    the summary — produces a different hash, so approval is bound to the
    EXACT reviewed change set."""
    canonical = json.dumps(
        {
            "summary": proposal.summary,
            "files": sorted(
                (
                    {
                        "path": item.path,
                        "change_type": item.change_type,
                        "original": item.original_content,
                        "new": item.new_content,
                    }
                    for item in files
                ),
                key=lambda entry: entry["path"],
            ),
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def approval_expiry() -> datetime:
    """When an approval granted now stops being applicable."""
    settings = get_settings()
    return _utcnow() + timedelta(hours=settings.apply_approval_ttl_hours)


def branch_name_for(task: CodingTask) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", task.description.lower()).strip("-")[:24]
    slug = slug.strip("-") or "change"
    return f"nish/task-{task.id.hex[:8]}-{slug}"


# ------------------------------------------------------------ apply helpers ---


def _load_approved(
    db: Session, task: CodingTask
) -> tuple[CodingProposal, list[CodingProposalFile], Approval]:
    proposal = db.scalar(
        select(CodingProposal)
        .where(CodingProposal.task_id == task.id)
        .order_by(CodingProposal.created_at.desc())
    )
    if proposal is None or proposal.status != "approved":
        raise HTTPException(status_code=409, detail="No approved proposal.")
    approval = db.scalar(
        select(Approval)
        .where(
            Approval.proposal_id == proposal.id,
            Approval.decision == "approved",
        )
        .order_by(Approval.decided_at.desc())
    )
    if approval is None or not approval.proposal_hash:
        raise HTTPException(
            status_code=409,
            detail="No recorded approval with an integrity hash.",
        )
    files = list(
        db.scalars(
            select(CodingProposalFile).where(
                CodingProposalFile.proposal_id == proposal.id
            )
        ).all()
    )
    if not files:
        raise HTTPException(status_code=409, detail="Proposal has no files.")
    return proposal, files, approval


def _ensure_not_expired(approval: Approval) -> None:
    expires_at = approval.expires_at
    if expires_at is None:
        raise HTTPException(
            status_code=409,
            detail="This approval predates integrity tracking — approve again.",
        )
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < _utcnow():
        raise HTTPException(
            status_code=409,
            detail=(
                "This approval has expired. Review the proposal and approve "
                "it again before applying."
            ),
        )


def _revalidate_files(
    repo: Path, task: CodingTask, files: list[CodingProposalFile]
) -> None:
    """Every safety rule from generation is enforced AGAIN against the
    real repository at application time: containment, protected files,
    binary block, size and count limits — and content drift (the file on
    disk must still be exactly what was reviewed as the original)."""
    settings = get_settings()
    if len(files) > settings.coding_max_modified_files:
        raise HTTPException(status_code=409, detail="Too many files in proposal.")
    guard = PathGuard(repo)
    total = 0
    for item in files:
        try:
            resolved = validate_target(
                guard,
                item.path,
                task.description,
                exists_required=(item.change_type == "modify"),
            )
        except HTTPException:
            raise
        except Exception as exc:  # PathAccessError / PatchValidationError
            reason = getattr(exc, "reason", None) or str(exc)
            raise HTTPException(
                status_code=409, detail=f"Refused path {item.path}: {reason}"
            )
        if "\x00" in item.new_content:
            raise HTTPException(
                status_code=409, detail=f"Binary content refused: {item.path}"
            )
        secret = detect_secret(item.new_content)
        if secret:
            raise HTTPException(
                status_code=409,
                detail=f"Refused {item.path}: proposed content contains {secret}.",
            )
        size = len(item.new_content.encode())
        if size > settings.coding_max_file_bytes:
            raise HTTPException(
                status_code=409, detail=f"File too large: {item.path}"
            )
        total += size
        if total > settings.coding_max_patch_bytes:
            raise HTTPException(status_code=409, detail="Proposal too large.")
        for pattern, message in _DANGEROUS_PATTERNS:
            if pattern in item.new_content and pattern not in item.original_content:
                raise HTTPException(
                    status_code=409,
                    detail=f"Security review failed for {item.path}: {message}",
                )
        if item.change_type == "modify":
            current = resolved.read_text(encoding="utf-8", errors="replace")
            if current != item.original_content:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"{item.path} changed since the proposal was reviewed. "
                        "Create a new task against the current code."
                    ),
                )
        elif resolved.exists():
            raise HTTPException(
                status_code=409,
                detail=f"{item.path} was created since review — refusing to overwrite.",
            )


def _restore(
    repo: Path,
    files: list[CodingProposalFile],
    original_branch: str,
    branch: str,
    branch_created: bool,
) -> None:
    """Return the repository to its exact pre-application state. File
    contents are restored from the reviewed snapshots (deterministic —
    no destructive git commands needed), then the original branch is
    checked out and the task branch deleted."""
    for item in files:
        try:
            target = (repo / item.path).resolve()
            if not str(target).startswith(str(repo.resolve())):
                continue  # never restore outside the repo
            if item.change_type == "create":
                target.unlink(missing_ok=True)
            else:
                target.write_text(item.original_content, encoding="utf-8")
        except Exception:  # noqa: BLE001 — restore must attempt every file
            continue
    if branch_created:
        try:
            gitops.checkout(repo, original_branch)
            gitops.delete_nish_branch(repo, branch)
        except gitops.GitError:
            pass  # branch left behind is annoying but safe; audited below


def _record_runs(
    db: Session, task: CodingTask, results: list[dict], phase: str
) -> None:
    for result in results:
        db.add(
            ValidationRun(
                task_id=task.id,
                command=result["command"],
                phase=phase,
                exit_code=result["exit_code"],
                duration_ms=result["duration_ms"],
                passed=result["passed"],
                timed_out=result["timed_out"],
                output_excerpt=result["output"],
            )
        )


def _run_validation(repo: Path, commands: list[str]) -> tuple[bool, list[dict]]:
    """Rerun the approved validation commands on the real branch, via the
    same allowlist executor used pre-approval. A rejected command counts
    as a failure — the allowlist is enforced at application time too."""
    results: list[dict] = []
    all_passed = True
    for command in commands:
        started = time.monotonic()
        try:
            outcome = run_allowlisted(command, cwd=repo)
            results.append(
                {
                    "command": command,
                    "exit_code": outcome.exit_code,
                    "duration_ms": outcome.duration_ms,
                    "passed": outcome.passed,
                    "timed_out": outcome.timed_out,
                    "output": (outcome.stdout + outcome.stderr)[:4000],
                }
            )
            if not outcome.passed:
                all_passed = False
        except CommandRejected as exc:
            results.append(
                {
                    "command": command,
                    "exit_code": None,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "passed": False,
                    "timed_out": False,
                    "output": f"REFUSED by policy: {exc.reason}",
                }
            )
            all_passed = False
    return all_passed, results


# ------------------------------------------------------------------- apply ---


def apply_proposal(
    db: Session,
    user: User,
    task: CodingTask,
    project: RegisteredProject,
    *,
    confirm: bool,
    expected_hash: str | None = None,
) -> ChangeApplication:
    settings = get_settings()
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                "Applying changes requires a second explicit confirmation: "
                'send {"confirm": true}.'
            ),
        )
    if task.state != "approved":
        raise HTTPException(
            status_code=409,
            detail="Only an approved task can be applied.",
        )

    proposal, files, approval = _load_approved(db, task)

    # Idempotency: an in-flight or committed application is returned
    # as-is instead of ever applying twice.
    existing = db.scalar(
        select(ChangeApplication)
        .where(
            ChangeApplication.task_id == task.id,
            ChangeApplication.status.in_(("applying", "committed")),
        )
        .order_by(ChangeApplication.created_at.desc())
    )
    if existing is not None:
        return existing

    _ensure_not_expired(approval)

    # Integrity: the proposal must hash to exactly what was approved,
    # and the caller's echoed hash (second confirmation) must match too.
    current_hash = compute_proposal_hash(proposal, files)
    if expected_hash is not None and expected_hash != approval.proposal_hash:
        raise HTTPException(
            status_code=409,
            detail=(
                "The confirmation hash does not match the approved proposal "
                "— refusing to apply. Reload the task and confirm again."
            ),
        )
    if current_hash != approval.proposal_hash:
        _audit().record(
            actor="coding_apply", action="hash_check", outcome="denied",
            task_id=str(task.id),
            detail={"expected": approval.proposal_hash, "actual": current_hash},
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "The proposal changed after it was reviewed and approved — "
                "refusing to apply. Review and approve it again."
            ),
        )

    # Repository preflight.
    try:
        repo = validate_project_root(project.root_path)
    except Exception as exc:  # noqa: BLE001 — surfaced as a clean 409
        raise HTTPException(status_code=409, detail=str(exc))
    if not gitops.is_git_repository(repo):
        raise HTTPException(
            status_code=409,
            detail="The project is not a Git repository — cannot apply safely.",
        )
    if gitops.configured_identity(repo) is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "No Git identity (user.name / user.email) is configured for "
                "this repository. NISH never invents one — configure it, "
                "then apply again."
            ),
        )
    if not gitops.is_clean(repo):
        raise HTTPException(
            status_code=409,
            detail=(
                "The repository has uncommitted changes. NISH refuses to "
                "apply onto a dirty working tree — commit or stash your "
                "work first, so nothing of yours can be mixed in or lost."
            ),
        )

    original_branch = gitops.current_branch(repo)
    original_head = gitops.head_commit(repo)
    branch = branch_name_for(task)

    if gitops.branch_exists(repo, branch):
        committed = db.scalar(
            select(ChangeApplication).where(
                ChangeApplication.task_id == task.id,
                ChangeApplication.branch_name == branch,
                ChangeApplication.status == "committed",
            )
        )
        if committed is not None:
            return committed
        raise HTTPException(
            status_code=409,
            detail=(
                f"Branch {branch} already exists and is not owned by a "
                "committed application of this task. Delete or rename it, "
                "then apply again."
            ),
        )

    _revalidate_files(repo, task, files)

    application = ChangeApplication(
        task_id=task.id,
        proposal_id=proposal.id,
        approval_id=approval.id,
        user_id=user.id,
        status="applying",
        branch_name=branch,
        original_branch=original_branch,
        original_head=original_head,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    _audit().record(
        actor="coding_apply", action="apply_start", outcome="ok",
        task_id=str(task.id),
        detail={"branch": branch, "original_branch": original_branch,
                "files": len(files), "proposal_hash": approval.proposal_hash},
    )

    branch_created = False
    try:
        gitops.create_branch(repo, branch)
        branch_created = True

        for item in files:
            target = repo / item.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item.new_content, encoding="utf-8")

        commands = list((task.plan or {}).get("validation_commands", []))
        passed, results = _run_validation(repo, commands)
        _record_runs(db, task, results, phase="apply")

        if not passed:
            _restore(repo, files, original_branch, branch, branch_created)
            application.status = "validation_failed"
            application.error = (
                "Validation failed on the feature branch — no commit was "
                "created and the repository was restored to its original "
                "state. The generated changes remain in the isolated "
                "workspace for inspection."
            )
            db.commit()
            _audit().record(
                actor="coding_apply", action="apply_validation", outcome="failed",
                task_id=str(task.id), detail={"branch": branch},
            )
            return application

        gitops.stage_paths(repo, [item.path for item in files])

        title = f"NISH: {proposal.summary.splitlines()[0][:68] or task.description[:68]}"
        body = (
            f"Task-ID: {task.id}\n"
            f"Proposal-ID: {proposal.id}\n"
            f"Validation: {len(results)} command(s) passed\n"
            "Created by NISH after explicit user approval."
        )
        commit_hash = gitops.commit(repo, title, body)

        application.commit_hash = commit_hash
        application.final_diff = gitops.diff_range(
            repo, original_head, commit_hash, settings.coding_max_patch_bytes
        )
        application.status = "committed"
        db.commit()
        _audit().record(
            actor="coding_apply", action="commit", outcome="ok",
            task_id=str(task.id),
            detail={"branch": branch, "commit": commit_hash},
        )
        return application

    except HTTPException:
        _restore(repo, files, original_branch, branch, branch_created)
        application.status = "failed"
        application.error = "Application aborted; repository restored."
        db.commit()
        raise
    except (gitops.GitError, OSError) as exc:
        _restore(repo, files, original_branch, branch, branch_created)
        application.status = "failed"
        application.error = f"Application failed: {exc}. Repository restored."
        db.commit()
        _audit().record(
            actor="coding_apply", action="apply", outcome="error",
            task_id=str(task.id), detail={"error": str(exc)[:200]},
        )
        raise HTTPException(status_code=500, detail=application.error)


# ---------------------------------------------------------------- rollback ---


def rollback_application(
    db: Session,
    user: User,
    task: CodingTask,
    project: RegisteredProject,
    *,
    confirm: bool,
) -> ChangeApplication:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail='Rollback requires explicit confirmation: send {"confirm": true}.',
        )
    application = db.scalar(
        select(ChangeApplication)
        .where(
            ChangeApplication.task_id == task.id,
            ChangeApplication.user_id == user.id,
        )
        .order_by(ChangeApplication.created_at.desc())
    )
    if application is None:
        raise HTTPException(status_code=404, detail="No application to roll back.")
    if application.status != "committed":
        raise HTTPException(
            status_code=409,
            detail=f"Nothing to roll back — application status is {application.status}.",
        )

    repo = validate_project_root(project.root_path)
    branch = application.branch_name

    if not gitops.branch_exists(repo, branch):
        raise HTTPException(
            status_code=409, detail=f"Branch {branch} no longer exists."
        )
    # The branch must contain EXACTLY the NISH commit on the recorded
    # base — anything else means the user built on it; refuse.
    head = gitops.branch_head(repo, branch)
    if head != application.commit_hash:
        raise HTTPException(
            status_code=409,
            detail=(
                "Unexpected commits were added on the task branch — NISH "
                "refuses to roll back over your work. Remove your commits "
                "or delete the branch manually."
            ),
        )
    if gitops.commit_parent(repo, head) != application.original_head:
        raise HTTPException(
            status_code=409,
            detail="Branch history does not match this application — refusing.",
        )

    if gitops.current_branch(repo) == branch:
        if gitops.has_tracked_changes(repo):
            raise HTTPException(
                status_code=409,
                detail=(
                    "You have uncommitted changes on the task branch. "
                    "Commit or stash them before rolling back."
                ),
            )
        gitops.checkout(repo, application.original_branch)
    gitops.delete_nish_branch(repo, branch)

    application.status = "rolled_back"
    application.rolled_back_at = _utcnow()
    db.commit()
    _audit().record(
        actor="coding_apply", action="rollback", outcome="ok",
        task_id=str(task.id),
        detail={"branch": branch, "commit": application.commit_hash},
    )
    return application
