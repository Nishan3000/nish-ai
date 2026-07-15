"""Project path rules for the coding agent.

Registration is the allowlist: only explicitly registered roots are ever
touched, and this module decides what a valid root is and which files
inside it exist as far as NISH is concerned.

Self-protection: the live NISH installation (backend AND frontend) can
never be registered, so the coding agent structurally cannot modify the
application that runs it.
"""

from collections.abc import Iterator
from pathlib import Path

from app.core.config import get_settings
from app.tools.path_guard import PathAccessError, PathGuard

# The running application's root (the directory containing backend/).
_APP_BACKEND_DIR = Path(__file__).resolve().parents[2]
NISH_ROOT = _APP_BACKEND_DIR.parent

# Directories whose CONTENTS never exist for the coding agent — on top
# of PathGuard's own denied directories (.git, node_modules, venvs,
# __pycache__): build outputs and caches.
EXTRA_IGNORED_DIRS: frozenset[str] = frozenset(
    {".next", "build", "dist", "target", ".pytest_cache", "coverage",
     ".mypy_cache", ".ruff_cache", "workspaces"}
)


class ProjectPathError(Exception):
    """Raised for any invalid or forbidden project root."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def validate_project_root(raw_path: str) -> Path:
    """Resolve and validate a path the user wants to register.

    Rules: must exist, be a directory, not be a filesystem root or home
    directory itself, and must not overlap the live NISH installation
    in either direction.
    """
    try:
        resolved = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise ProjectPathError("Path does not exist or cannot be resolved.")
    if not resolved.is_dir():
        raise ProjectPathError("Path is not a directory.")
    if resolved == resolved.anchor or resolved == Path(resolved.anchor):
        raise ProjectPathError("Refusing to register a filesystem root.")
    if resolved == Path.home():
        raise ProjectPathError(
            "Refusing to register your entire home directory — register a "
            "specific project folder instead."
        )
    # Self-protection, both directions: the project must not contain the
    # NISH installation, and must not live inside it.
    if resolved == NISH_ROOT or resolved in NISH_ROOT.parents:
        raise ProjectPathError(
            "This path contains the running NISH installation. NISH does "
            "not modify itself."
        )
    if NISH_ROOT in resolved.parents:
        raise ProjectPathError(
            "This path is inside the running NISH installation. NISH does "
            "not modify itself."
        )
    return resolved


def make_guard(project_root: Path) -> PathGuard:
    """A PathGuard rooted at a validated project root."""
    return PathGuard(project_root)


def is_visible(guard: PathGuard, path: Path) -> bool:
    """True if a file inside the root is readable under all rules
    (containment, no secrets, no ignored directories)."""
    relative = path.relative_to(guard.root)
    if any(part in EXTRA_IGNORED_DIRS for part in relative.parts):
        return False
    try:
        guard.resolve(relative.as_posix())
        return True
    except PathAccessError:
        return False


def iter_project_files(guard: PathGuard) -> Iterator[tuple[str, int]]:
    """Yield (relative_path, size) for every visible file, enforcing the
    repository size limits. Raises ProjectPathError when limits are hit
    — a repository too large to reason about is refused, not truncated
    silently."""
    settings = get_settings()
    total_files = 0
    total_bytes = 0
    for path in sorted(guard.root.rglob("*")):
        if not path.is_file():
            continue
        if not is_visible(guard, path):
            continue
        size = path.stat().st_size
        if size > settings.coding_max_file_bytes:
            continue  # oversized single files simply don't exist for us
        total_files += 1
        total_bytes += size
        if total_files > settings.coding_max_repo_files:
            raise ProjectPathError(
                f"Repository exceeds {settings.coding_max_repo_files} files."
            )
        if total_bytes > settings.coding_max_repo_bytes:
            raise ProjectPathError("Repository exceeds the size limit.")
        yield path.relative_to(guard.root).as_posix(), size
