"""Schemas for the coding-agent API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.coding.planner import CodingPlan


class ProjectRegister(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    root_path: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=500)
    default_branch: str = Field(default="main", max_length=80)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    root_path: str
    description: str
    default_branch: str
    created_at: datetime
    updated_at: datetime
    last_scanned_at: datetime | None


class ScanOut(BaseModel):
    files: list[dict]
    technologies: list[str]
    readme_excerpt: str
    dependency_files: list[str]
    test_commands: list[str]
    git_branch: str | None
    git_dirty_files: int | None


class TaskCreate(BaseModel):
    project_id: uuid.UUID
    description: str = Field(min_length=10, max_length=4_000)


class ProposalFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    path: str
    change_type: str


class ValidationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    command: str
    exit_code: int | None
    duration_ms: int
    passed: bool
    timed_out: bool
    output_excerpt: str


class FindingOut(BaseModel):
    severity: str
    path: str
    message: str


class ReviewOut(BaseModel):
    findings: list[FindingOut]
    notes: list[str]
    tests_ran: bool
    tests_passed: bool
    ready_for_approval: bool


class ProposalOut(BaseModel):
    id: uuid.UUID
    status: str
    summary: str
    diff: str
    files: list[ProposalFileOut]
    warnings: list[str]
    created_at: datetime


class ApprovalOut(BaseModel):
    """The recorded decision, with the integrity hash and expiry that
    bind it to the exact reviewed proposal."""

    model_config = ConfigDict(from_attributes=True)

    decision: str
    note: str
    proposal_hash: str | None
    expires_at: datetime | None
    decided_at: datetime


class ApplicationOut(BaseModel):
    """One attempt to apply an approved proposal to the repository."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str  # applying | validation_failed | failed | committed | rolled_back
    branch_name: str
    original_branch: str
    original_head: str
    commit_hash: str | None
    final_diff: str
    error: str | None
    created_at: datetime
    rolled_back_at: datetime | None


class ApplyRequest(BaseModel):
    """Second explicit confirmation. `proposal_hash` must echo the hash
    shown at approval time, binding the confirmation to the exact
    reviewed change set."""

    confirm: bool = False
    proposal_hash: str = Field(min_length=64, max_length=64)


class RollbackRequest(BaseModel):
    confirm: bool = False


class TaskOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    description: str
    state: str
    plan: CodingPlan | None
    error: str | None
    created_at: datetime
    proposal: ProposalOut | None = None
    validation_runs: list[ValidationRunOut] = []
    review: ReviewOut | None = None
    # v0.7: recorded decision + application lifecycle (additive fields).
    approval: ApprovalOut | None = None
    application: ApplicationOut | None = None


class ValidateRequest(BaseModel):
    commands: list[str] = Field(min_length=1, max_length=6)


class DecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=500)


class DecisionOut(BaseModel):
    decision: str
    message: str
    proposal_hash: str | None = None
    expires_at: datetime | None = None
