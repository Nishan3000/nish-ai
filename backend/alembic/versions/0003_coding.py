"""coding agent: projects, tasks, proposals, validations, approvals

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "registered_projects",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("root_path", sa.String(500), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("default_branch", sa.String(80), nullable=False, server_default="main"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_registered_projects_user_id", "registered_projects", ["user_id"])

    op.create_table(
        "coding_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(),
                  sa.ForeignKey("registered_projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="created"),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("workspace_path", sa.String(500), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_coding_tasks_user_id", "coding_tasks", ["user_id"])

    op.create_table(
        "coding_proposals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("task_id", sa.Uuid(),
                  sa.ForeignKey("coding_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("diff", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "coding_proposal_files",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"),
                  primary_key=True, autoincrement=True),
        sa.Column("proposal_id", sa.Uuid(),
                  sa.ForeignKey("coding_proposals.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("change_type", sa.String(16), nullable=False),
        sa.Column("original_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("new_content", sa.Text(), nullable=False),
    )

    op.create_table(
        "validation_runs",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"),
                  primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Uuid(),
                  sa.ForeignKey("coding_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("command", sa.String(300), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("timed_out", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("output_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "approvals",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"),
                  primary_key=True, autoincrement=True),
        sa.Column("proposal_id", sa.Uuid(),
                  sa.ForeignKey("coding_proposals.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("approvals")
    op.drop_table("validation_runs")
    op.drop_table("coding_proposal_files")
    op.drop_table("coding_proposals")
    op.drop_index("ix_coding_tasks_user_id", table_name="coding_tasks")
    op.drop_table("coding_tasks")
    op.drop_index("ix_registered_projects_user_id", table_name="registered_projects")
    op.drop_table("registered_projects")
