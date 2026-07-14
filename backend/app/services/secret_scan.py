"""Secret-pattern detection for memory content.

Long-term memory must never become a credential store: memories persist,
get injected into prompts, and appear in the UI, so a stored secret
would leak repeatedly. Before any memory is saved, its content is
scanned here; anything credential-shaped is rejected with a clear reason
(and the reason never echoes the secret back).

Detection is deliberately pattern-based and conservative — it catches
obvious credentials (the requirement), not every conceivable encoding.
"""

import re

# (pattern, human-readable reason) — reasons never include the match.
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "an API key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "a GitHub token"),
    (re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"), "a GitHub token"),
    (re.compile(r"\bxox[bpars]-[A-Za-z0-9-]{10,}\b"), "a Slack token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "an AWS access key"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}\b", re.IGNORECASE), "a bearer token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "a private key"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"), "a JWT token"),
    (
        re.compile(
            r"\b(password|passwd|pwd|passphrase)\b\s*(is|was|[:=])\s*\S+",
            re.IGNORECASE,
        ),
        "a password",
    ),
    (
        re.compile(
            r"\b(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token"
            r"|client[_-]?secret|private[_-]?key)\b\s*[:=]\s*\S+",
            re.IGNORECASE,
        ),
        "a credential assignment",
    ),
    (
        # Environment-variable style assignment to a secret-ish name.
        re.compile(
            r"\b(export\s+)?[A-Z][A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD|PASSWD)"
            r"[A-Z0-9_]*\s*=\s*\S+"
        ),
        "an environment variable containing a secret",
    ),
    (
        # Long high-entropy-looking blobs (hex or base64-ish, 40+ chars).
        re.compile(r"\b[A-Fa-f0-9]{40,}\b"),
        "a long hexadecimal token",
    ),
]


def detect_secret(content: str) -> str | None:
    """Return a human-readable reason if content looks like a secret,
    or None if it appears safe to store."""
    for pattern, reason in _SECRET_PATTERNS:
        if pattern.search(content):
            return reason
    return None
