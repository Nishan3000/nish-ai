"""Deterministic review of a proposal.

Three stages, all rule-based rather than model-based on purpose: a
review that gates approval must be reproducible and testable, not
subject to model mood. (A model-written narrative review can be layered
on later; it must never be the gate.)

  1. Code review    — structural checks on the changed files.
  2. Test review    — did every validation run pass?
  3. Security review — secret patterns and dangerous constructs in the
                       NEW content, protected paths touched.

`ready_for_approval` is the conjunction: no high-severity security
findings, at least one validation run, and all validations passed.
"""

from dataclasses import dataclass, field

from app.coding.generator import ProposedFile, is_protected_path
from app.services.secret_scan import detect_secret

_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    ("shell=True", "subprocess with shell=True enables command injection"),
    ("os.system(", "os.system executes through a shell"),
    ("eval(", "eval executes arbitrary code"),
    ("exec(", "exec executes arbitrary code"),
    ("curl ", "network download in code"),
    ("wget ", "network download in code"),
    ("rm -rf", "destructive shell command in code"),
    ("dangerouslySetInnerHTML", "raw HTML injection point"),
]


@dataclass
class Finding:
    severity: str  # "high" | "warning"
    path: str
    message: str


@dataclass
class ReviewResult:
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    tests_passed: bool = False
    tests_ran: bool = False
    ready_for_approval: bool = False


def review_proposal(
    files: list[ProposedFile],
    validation_results: list[dict],
    generation_warnings: list[str],
) -> ReviewResult:
    result = ReviewResult()

    # 1. Code review — structural notes.
    for item in files:
        removed = len(item.original_content.splitlines()) - len(
            item.new_content.splitlines()
        )
        if item.change_type == "modify" and removed > 50:
            result.findings.append(
                Finding("warning", item.path,
                        f"removes {removed} lines — verify nothing needed was lost")
            )
        if "TODO" in item.new_content or "FIXME" in item.new_content:
            result.notes.append(f"{item.path}: contains TODO/FIXME markers")

    # 2. Test-result review.
    result.tests_ran = len(validation_results) > 0
    result.tests_passed = result.tests_ran and all(
        run.get("passed") for run in validation_results
    )
    if not result.tests_ran:
        result.notes.append("No validation commands were run.")
    elif not result.tests_passed:
        failed = [r["command"] for r in validation_results if not r.get("passed")]
        result.notes.append(f"Failing validation: {', '.join(failed)}")

    # 3. Security review of the NEW content only.
    for item in files:
        secret_reason = detect_secret(item.new_content)
        if secret_reason:
            result.findings.append(
                Finding("high", item.path,
                        f"generated content appears to contain {secret_reason}")
            )
        for pattern, message in _DANGEROUS_PATTERNS:
            if pattern in item.new_content and pattern not in item.original_content:
                result.findings.append(Finding("warning", item.path, message))
        if is_protected_path(item.path):
            result.findings.append(
                Finding("warning", item.path,
                        "modifies a security-related file (explicitly requested)")
            )

    for warning in generation_warnings:
        result.notes.append(warning)

    has_high = any(f.severity == "high" for f in result.findings)
    result.ready_for_approval = (
        len(files) > 0 and result.tests_ran and result.tests_passed and not has_high
    )
    return result
