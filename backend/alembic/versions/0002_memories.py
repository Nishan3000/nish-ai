"""memories: long-term memory table

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Plain UUID for now; the FK arrives with the projects milestone.
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("importance_score", sa.Float(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
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
        sa.CheckConstraint(
            "memory_type IN ('user_preference','personal_fact','project_fact',"
            "'goal','correction','successful_outcome','failed_outcome','custom')",
            name="ck_memories_type",
        ),
        sa.CheckConstraint(
            "importance_score >= 0 AND importance_score <= 1",
            name="ck_memories_importance",
        ),
    )
    op.create_index(
        "ix_memories_user_active", "memories", ["user_id", "is_active"]
    )


def downgrade() -> None:
    op.drop_index("ix_memories_user_active", table_name="memories")
    op.drop_table("memories")
