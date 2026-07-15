"""Isolated workspace manager.

Every coding task gets its own directory under the configured workspace
root containing a COPY of the registered project. The original
repository is never written to; the copy itself is the sandbox, and the
untouched original is the rollback path. Git worktrees were considered
and rejected for this milestone: registered projects are not guaranteed
to be Git repositories, and a plain bounded copy is simpler to reason
about and equally isolated.

What is copied: only files visible under the project's PathGuard —
which means secret files (.env*, keys, credentials) and ignored
directories are NEVER present in the workspace at all. The model and
every validation command physically cannot read what isn't there.
"""

import shutil
import time
import uuid
from pathlib import Path

from app.coding.paths import iter_project_files
from app.core.audit import get_audit_logger
from app.core.config import get_settings
from app.tools.path_guard import PathGuard


class WorkspaceError(Exception):
    pass


def _workspace_root() -> Path:
    root = Path(get_settings().coding_workspace_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _audit():
    return get_audit_logger(get_settings().agent_audit_log_path)


def create_workspace(project_guard: PathGuard, task_id: uuid.UUID) -> Path:
    """Copy the visible project into a fresh per-task directory."""
    cleanup_expired()  # lazy sweep of abandoned workspaces
    workspace = _workspace_root() / str(task_id)
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)

    copied_files = 0
    copied_bytes = 0
    for relative, size in iter_project_files(project_guard):
        source = project_guard.root / relative
        destination = workspace / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied_files += 1
        copied_bytes += size

    _audit().record(
        actor="coding_workspace", action="create", outcome="ok",
        detail={
            "task_id": str(task_id),
            "files": copied_files,
            "bytes": copied_bytes,
        },
    )
    return workspace


def workspace_guard(workspace: Path) -> PathGuard:
    """All reads/writes inside the workspace go through their own guard:
    containment, secret-name blocking, and ignored-directory rules apply
    to generated changes exactly as they do to the original project."""
    return PathGuard(workspace)


def cleanup_workspace(task_id: uuid.UUID) -> bool:
    workspace = _workspace_root() / str(task_id)
    if not workspace.exists():
        return False
    shutil.rmtree(workspace)
    _audit().record(
        actor="coding_workspace", action="cleanup", outcome="ok",
        detail={"task_id": str(task_id)},
    )
    return True


def cleanup_expired() -> int:
    """Remove workspaces older than the configured TTL."""
    settings = get_settings()
    cutoff = time.time() - settings.coding_workspace_ttl_hours * 3600
    removed = 0
    root = _workspace_root()
    for entry in root.iterdir():
        if entry.is_dir() and entry.stat().st_mtime < cutoff:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    if removed:
        _audit().record(
            actor="coding_workspace", action="cleanup_expired", outcome="ok",
            detail={"removed": removed},
        )
    return removed
