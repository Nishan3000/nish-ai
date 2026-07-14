"""Read-only repository tools.

These are the ONLY ways the agent can see the codebase. Every call:
  * passes through the ToolRegistry permission check,
  * passes through PathGuard,
  * is written to the audit log with its outcome.

No tool in this module can write, delete, or execute anything.
"""

from dataclasses import dataclass
from pathlib import Path

from app.core.audit import AuditLogger
from app.tools.path_guard import PathAccessError, PathGuard
from app.tools.permissions import Capability, ToolRegistry


@dataclass(frozen=True)
class TreeEntry:
    """One file in the workspace listing."""

    path: str          # relative to the workspace root, POSIX separators
    size_bytes: int


@dataclass(frozen=True)
class FileContent:
    """A safely read text file."""

    path: str
    content: str
    truncated: bool


@dataclass(frozen=True)
class SearchHit:
    """One matching line from a content search."""

    path: str
    line_number: int
    line: str


class RepoReader:
    """Bounded, audited, read-only view of the workspace."""

    def __init__(
        self,
        guard: PathGuard,
        registry: ToolRegistry,
        audit: AuditLogger,
        *,
        max_read_bytes: int,
        max_tree_entries: int,
    ) -> None:
        self._guard = guard
        self._registry = registry
        self._audit = audit
        self._max_read_bytes = max_read_bytes
        self._max_tree_entries = max_tree_entries

    # ------------------------------------------------------------ tools ---

    def list_tree(
        self,
        granted: frozenset[Capability],
        task_id: str | None = None,
    ) -> list[TreeEntry]:
        """List every readable file under the root (bounded)."""
        self._registry.check("repo.list_tree", granted, task_id)
        entries: list[TreeEntry] = []
        for path in sorted(self._guard.root.rglob("*")):
            if len(entries) >= self._max_tree_entries:
                break
            if not path.is_file():
                continue
            relative = path.relative_to(self._guard.root).as_posix()
            try:
                self._guard.resolve(relative)  # skip denied/secret files
            except PathAccessError:
                continue
            entries.append(
                TreeEntry(path=relative, size_bytes=path.stat().st_size)
            )
        self._audit.record(
            actor="repo_reader",
            action="list_tree",
            outcome="ok",
            task_id=task_id,
            detail={"entries": len(entries)},
        )
        return entries

    def read_file(
        self,
        relative_path: str,
        granted: frozenset[Capability],
        task_id: str | None = None,
    ) -> FileContent:
        """Read one text file, bounded by size, refusing binaries."""
        self._registry.check("repo.read_file", granted, task_id)
        try:
            path = self._guard.resolve(relative_path)
            if not path.is_file():
                raise PathAccessError(relative_path, "not a file")
            if self._guard.is_probably_binary(path):
                raise PathAccessError(relative_path, "binary file")
        except PathAccessError as exc:
            self._audit.record(
                actor="repo_reader",
                action="read_file",
                outcome="denied",
                task_id=task_id,
                detail={"path": relative_path, "reason": exc.reason},
            )
            raise

        raw = path.read_bytes()
        truncated = len(raw) > self._max_read_bytes
        text = raw[: self._max_read_bytes].decode("utf-8", errors="replace")
        self._audit.record(
            actor="repo_reader",
            action="read_file",
            outcome="ok",
            task_id=task_id,
            detail={"path": relative_path, "bytes": len(raw), "truncated": truncated},
        )
        return FileContent(path=relative_path, content=text, truncated=truncated)

    def search(
        self,
        needle: str,
        granted: frozenset[Capability],
        task_id: str | None = None,
        max_hits: int = 100,
    ) -> list[SearchHit]:
        """Case-insensitive substring search across readable text files."""
        self._registry.check("repo.search", granted, task_id)
        needle_lowered = needle.lower()
        hits: list[SearchHit] = []
        for entry in self.list_tree(granted, task_id):
            if len(hits) >= max_hits:
                break
            path = self._guard.root / entry.path
            if self._guard.is_probably_binary(path):
                continue
            text = path.read_bytes()[: self._max_read_bytes].decode(
                "utf-8", errors="replace"
            )
            for line_number, line in enumerate(text.splitlines(), start=1):
                if needle_lowered in line.lower():
                    hits.append(
                        SearchHit(
                            path=entry.path,
                            line_number=line_number,
                            line=line.strip()[:300],
                        )
                    )
                    if len(hits) >= max_hits:
                        break
        self._audit.record(
            actor="repo_reader",
            action="search",
            outcome="ok",
            task_id=task_id,
            detail={"needle": needle[:100], "hits": len(hits)},
        )
        return hits
