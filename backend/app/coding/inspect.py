"""Safe repository inspection for the coding agent.

Everything here is read-only, bounded, and routed through PathGuard.
Git information comes from the read-only allowlisted executor — never
from .git internals (which can carry credentials in remote URLs).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.coding.executor import CommandRejected, run_allowlisted
from app.coding.paths import is_visible, iter_project_files
from app.core.audit import get_audit_logger
from app.core.config import get_settings
from app.tools.path_guard import PathAccessError, PathGuard

# filename/dirname markers -> technology label
_TECH_MARKERS: list[tuple[str, str]] = [
    ("package.json", "Node.js"),
    ("tsconfig.json", "TypeScript"),
    ("next.config.js", "Next.js"),
    ("next.config.ts", "Next.js"),
    ("requirements.txt", "Python"),
    ("pyproject.toml", "Python"),
    ("alembic.ini", "Alembic"),
    ("Cargo.toml", "Rust"),
    ("go.mod", "Go"),
    ("docker-compose.yml", "Docker Compose"),
    ("Dockerfile", "Docker"),
    ("tailwind.config.js", "Tailwind CSS"),
    ("pytest.ini", "pytest"),
]

_DEPENDENCY_FILES = (
    "package.json", "requirements.txt", "pyproject.toml", "Cargo.toml", "go.mod",
)
_README_NAMES = ("README.md", "README.rst", "README.txt", "readme.md")


@dataclass
class ProjectInspection:
    """Everything the planner (and the user) sees about a repository."""

    files: list[dict[str, object]] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    readme_excerpt: str = ""
    dependency_excerpts: dict[str, str] = field(default_factory=dict)
    test_commands: list[str] = field(default_factory=list)
    git_branch: str | None = None
    git_dirty_files: int | None = None


def _audit():
    return get_audit_logger(get_settings().agent_audit_log_path)


def read_file(guard: PathGuard, relative_path: str) -> tuple[str, bool]:
    """Bounded, guarded read of one text file → (content, truncated)."""
    settings = get_settings()
    path = guard.resolve(relative_path)
    if not path.is_file():
        raise PathAccessError(relative_path, "not a file")
    if guard.is_probably_binary(path):
        raise PathAccessError(relative_path, "binary file")
    raw = path.read_bytes()
    truncated = len(raw) > settings.coding_max_file_bytes
    text = raw[: settings.coding_max_file_bytes].decode("utf-8", errors="replace")
    _audit().record(
        actor="coding_inspect", action="read_file", outcome="ok",
        detail={"path": relative_path, "bytes": len(raw)},
    )
    return text, truncated


def search(
    guard: PathGuard, needle: str, *, in_names: bool, max_hits: int = 100
) -> list[dict[str, object]]:
    """Case-insensitive search in filenames or file contents."""
    needle_lowered = needle.lower()
    hits: list[dict[str, object]] = []
    for relative, _size in iter_project_files(guard):
        if len(hits) >= max_hits:
            break
        if in_names:
            if needle_lowered in relative.lower():
                hits.append({"path": relative})
            continue
        path = guard.root / relative
        if guard.is_probably_binary(path):
            continue
        text = path.read_bytes()[:200_000].decode("utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if needle_lowered in line.lower():
                hits.append(
                    {"path": relative, "line": line_number,
                     "text": line.strip()[:300]}
                )
                if len(hits) >= max_hits:
                    break
    _audit().record(
        actor="coding_inspect", action="search", outcome="ok",
        detail={"needle": needle[:80], "in_names": in_names, "hits": len(hits)},
    )
    return hits


def _detect_test_commands(guard: PathGuard, files: set[str]) -> list[str]:
    """Derive validation commands from KNOWN configuration files only —
    never invented, never arbitrary."""
    commands: list[str] = []
    if "package.json" in files:
        try:
            raw, _ = read_file(guard, "package.json")
            scripts = json.loads(raw).get("scripts", {})
            if "test" in scripts:
                commands.append("npm test")
            for script in ("lint", "build", "typecheck"):
                if script in scripts:
                    commands.append(f"npm run {script}")
        except (PathAccessError, ValueError):
            pass
        if "tsconfig.json" in files and "npx tsc --noEmit" not in commands:
            commands.append("npx tsc --noEmit")
    if {"pytest.ini", "pyproject.toml", "setup.cfg"} & files or any(
        name.startswith("tests/") or name.startswith("test_") for name in files
    ):
        commands.append("pytest")
    return commands


def _git_info(project_root: Path) -> tuple[str | None, int | None]:
    """Branch name and dirty-file count via read-only git commands.
    Credentials are never touched: we execute `git status`/`rev-parse`
    (allowlisted, read-only) instead of reading .git internals."""
    if not (project_root / ".git").exists():
        return None, None
    try:
        branch_result = run_allowlisted(
            "git rev-parse --abbrev-ref HEAD", cwd=project_root
        )
        status_result = run_allowlisted(
            "git status --porcelain", cwd=project_root
        )
    except CommandRejected:  # pragma: no cover — both are allowlisted
        return None, None
    branch = branch_result.stdout.strip() if branch_result.exit_code == 0 else None
    dirty = (
        len([line for line in status_result.stdout.splitlines() if line.strip()])
        if status_result.exit_code == 0
        else None
    )
    return branch, dirty


def inspect_project(guard: PathGuard) -> ProjectInspection:
    """Full bounded inspection used by the scan endpoint and planner."""
    inspection = ProjectInspection()
    names: set[str] = set()
    for relative, size in iter_project_files(guard):
        inspection.files.append({"path": relative, "size_bytes": size})
        names.add(relative)

    inspection.technologies = sorted(
        {label for marker, label in _TECH_MARKERS if marker in names}
    )
    if "requirements.txt" in names:
        try:
            deps, _ = read_file(guard, "requirements.txt")
            if "fastapi" in deps.lower():
                inspection.technologies.append("FastAPI")
        except PathAccessError:
            pass

    for readme in _README_NAMES:
        if readme in names:
            try:
                content, _ = read_file(guard, readme)
                inspection.readme_excerpt = content[:2_000]
            except PathAccessError:
                pass
            break

    for dependency_file in _DEPENDENCY_FILES:
        if dependency_file in names:
            try:
                content, _ = read_file(guard, dependency_file)
                inspection.dependency_excerpts[dependency_file] = content[:1_500]
            except PathAccessError:
                pass

    inspection.test_commands = _detect_test_commands(guard, names)
    inspection.git_branch, inspection.git_dirty_files = _git_info(guard.root)

    _audit().record(
        actor="coding_inspect", action="inspect_project", outcome="ok",
        detail={
            "files": len(inspection.files),
            "technologies": inspection.technologies,
        },
    )
    return inspection


def build_tree_text(files: list[dict[str, object]], max_entries: int = 400) -> str:
    """Compact indented tree for prompts and the UI."""
    lines: list[str] = []
    for entry in files[:max_entries]:
        path = str(entry["path"])
        depth = path.count("/")
        name = path.rsplit("/", 1)[-1]
        lines.append(f"{'  ' * depth}{name}")
    if len(files) > max_entries:
        lines.append(f"… and {len(files) - max_entries} more files")
    return "\n".join(lines)
