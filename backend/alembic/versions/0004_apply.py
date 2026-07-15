"""reviewed change application: approval integrity, apply lifecycle

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "approvals",
        sa.Column("proposal_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "approvals",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "validation_runs",
        sa.Column(
            "phase",
            sa.String(length=16),
            nullable=False,
            server_default="workspace",
        ),
    )
    op.create_table(
        "change_applications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey("coding_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "proposal_id",
            sa.Uuid(),
            sa.ForeignKey("coding_proposals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "approval_id",
            sa.Integer(),
            sa.ForeignKey("approvals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("branch_name", sa.String(length=200), nullable=False),
        sa.Column("original_branch", sa.String(length=200), nullable=False),
        sa.Column("original_head", sa.String(length=64), nullable=False),
        sa.Column("commit_hash", sa.String(length=64), nullable=True),
        sa.Column("final_diff", sa.Text(), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_change_applications_task", "change_applications", ["task_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_change_applications_task", table_name="change_applications")
    op.drop_table("change_applications")
    op.drop_column("validation_runs", "phase")
    op.drop_column("approvals", "expires_at")
    op.drop_column("approvals", "proposal_hash")
