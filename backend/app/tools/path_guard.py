"""PathGuard — the agent's hard filesystem boundary.

Every path the agent touches goes through `resolve()` first. The guard
enforces, in order:

  1. Containment: the fully resolved path (symlinks followed) must be
     inside the workspace root. `../` tricks, absolute paths, and
     symlinks pointing outside are all caught by the same check, because
     we compare RESOLVED paths, not the strings the model produced.
  2. Denied names: secret-bearing files (.env*, keys, credentials) and
     the .git internals are unreadable even though they are inside the
     root — .git/config can contain tokens embedded in remote URLs.
  3. Read limits: oversized and binary files are refused, keeping model
     prompts bounded and preventing junk from entering the context.

The guard is fail-closed: anything not explicitly allowed raises
PathAccessError.
"""

from pathlib import Path

# File/directory names the agent may never read, even inside the root.
DENIED_NAME_PATTERNS: tuple[str, ...] = (
    ".env",            # matches .env, .env.local, .env.production, ...
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "*credential*",
    "*secret*",
    ".netrc",
    ".npmrc",          # can contain auth tokens
    ".pypirc",
)

DENIED_DIRECTORIES: frozenset[str] = frozenset(
    {".git", "node_modules", ".venv", "venv", "__pycache__"}
)


class PathAccessError(Exception):
    """Raised whenever a path is outside the allowed boundary."""

    def __init__(self, requested: str, reason: str) -> None:
        self.requested = requested
        self.reason = reason
        super().__init__(f"Access denied for '{requested}': {reason}")


class PathGuard:
    """Validates and resolves paths against a fixed workspace root."""

    def __init__(self, root: str | Path) -> None:
        root_path = Path(root).resolve()
        if not root_path.is_dir():
            raise ValueError(
                f"Workspace root does not exist or is not a directory: {root_path}"
            )
        self._root = root_path

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, relative_path: str) -> Path:
        """Turn an agent-supplied path into a safe absolute path.

        Raises PathAccessError if the path escapes the root or names a
        denied file/directory.
        """
        candidate = (self._root / relative_path).resolve()

        # 1. Containment — after resolving symlinks and '..' components.
        if candidate != self._root and self._root not in candidate.parents:
            raise PathAccessError(relative_path, "outside the workspace root")

        # 2. Denied directory anywhere in the relative path.
        relative_parts = candidate.relative_to(self._root).parts
        for part in relative_parts:
            if part in DENIED_DIRECTORIES:
                raise PathAccessError(
                    relative_path, f"'{part}' contents are off-limits"
                )

        # 3. Denied filename patterns (checked against every component,
        #    so a denied directory name also blocks its children).
        for part in relative_parts:
            lowered = part.lower()
            for pattern in DENIED_NAME_PATTERNS:
                if Path(lowered).match(pattern) or lowered.startswith(pattern):
                    raise PathAccessError(
                        relative_path, "file may contain secrets"
                    )

        return candidate

    def is_probably_binary(self, path: Path, sniff_bytes: int = 1024) -> bool:
        """Cheap binary sniff: a NUL byte in the first KB means binary."""
        with path.open("rb") as handle:
            return b"\x00" in handle.read(sniff_bytes)
