"""Append-only, tamper-evident audit log.

Every agent action — every tool call, permission decision, and state
transition — is recorded here. Design properties:

  * Append-only JSONL: one JSON object per line, never rewritten.
  * Hash-chained: each record stores the SHA-256 of the previous record,
    so deleting or editing any line breaks the chain. `verify_chain()`
    detects tampering. The agent has no tool that can write to this file;
    only this module appends to it.
  * Redaction: values that look like secrets (API keys, tokens,
    passwords) are masked BEFORE being written, so the log itself can
    never leak credentials.

The logger deliberately has no "disable" switch and no delete method:
per the security requirements, the agent must not be able to turn off
audit logging.
"""

import hashlib
import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64

# Keys whose values are always masked, wherever they appear.
_SECRET_KEY_PATTERN = re.compile(
    r"(secret|password|passwd|token|api[_-]?key|authorization|credential|private[_-]?key)",
    re.IGNORECASE,
)

# Values that look like credentials even under an innocent key.
_SECRET_VALUE_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),              # common API-key shape
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}\b"),       # bearer tokens
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),                # GitHub tokens
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                    # AWS access keys
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),      # PEM keys
]

REDACTED = "[REDACTED]"


def redact(value: Any) -> Any:
    """Recursively mask anything secret-looking in a JSON-able structure."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if _SECRET_KEY_PATTERN.search(str(key)) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        result = value
        for pattern in _SECRET_VALUE_PATTERNS:
            result = pattern.sub(REDACTED, result)
        return result
    return value


class AuditLogger:
    """Hash-chained JSONL audit log. Thread-safe within one process."""

    def __init__(self, log_path: str | Path) -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_hash = self._load_last_hash()

    @property
    def path(self) -> Path:
        return self._path

    def _load_last_hash(self) -> str:
        """Resume the chain from the last record on disk (if any)."""
        if not self._path.exists():
            return GENESIS_HASH
        last_line = ""
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    last_line = line
        if not last_line:
            return GENESIS_HASH
        try:
            return str(json.loads(last_line)["hash"])
        except (ValueError, KeyError):
            # Corrupt tail: keep appending, verification will flag it.
            logger.error("Audit log tail is corrupt; chain will not verify.")
            return GENESIS_HASH

    def record(
        self,
        *,
        actor: str,
        action: str,
        outcome: str,
        task_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one audit record and return it.

        Args:
            actor: which component acted, e.g. "planner", "repo_reader".
            action: what happened, e.g. "read_file", "state_transition".
            outcome: "ok", "denied", or "error".
            task_id: agent task this belongs to, if any.
            detail: extra context; redacted before writing.
        """
        with self._lock:
            body = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "task_id": task_id,
                "actor": actor,
                "action": action,
                "outcome": outcome,
                "detail": redact(detail or {}),
                "prev_hash": self._last_hash,
            }
            canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
            body["hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(body, separators=(",", ":")) + "\n")
            self._last_hash = body["hash"]
            return body

    def verify_chain(self) -> tuple[bool, str]:
        """Re-walk the log and check every hash. Returns (ok, message)."""
        if not self._path.exists():
            return True, "empty log"
        prev = GENESIS_HASH
        with self._path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    return False, f"line {line_number}: not valid JSON"
                stored_hash = record.pop("hash", None)
                if record.get("prev_hash") != prev:
                    return False, f"line {line_number}: broken chain link"
                canonical = json.dumps(
                    record, sort_keys=True, separators=(",", ":")
                )
                expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                if stored_hash != expected:
                    return False, f"line {line_number}: record was modified"
                prev = stored_hash
        return True, "chain intact"
