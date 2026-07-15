"""ORM models — part 1 of the memory milestone.

Tables: users, conversations, messages. (memories, projects, and
feedback arrive with the long-term-memory part, via their own Alembic
migration — nothing here will need to change.)

Design notes:
  * UUID primary keys via SQLAlchemy's portable `Uuid` type: native UUID
    on PostgreSQL, CHAR on SQLite (which the tests use).
  * Deleting a conversation cascades to its messages at the DATABASE
    level (ondelete="CASCADE"), so orphans are impossible even if
    application code is bypassed.
  * `Message.role` is constrained by a CHECK to 'user'/'assistant' —
    the same rule the API schema enforces, repeated at the storage layer
    as defence in depth (a stored 'system' row could otherwise smuggle
    instructions into future model calls).
  * Timestamps are set by the database (func.now()), not Python, so they
    are consistent even with multiple app processes.

There is no authentication yet (that phase is still ahead), so a single
"local" user row owns everything. Every query in the API layer STILL
filters by user_id — the ownership checks are real and tested; only the
"who is the current user" part is a stub that the auth phase replaces.
"""

import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Declarative base shared by all NISH models."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(80), unique=True, nullable=False
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(120), nullable=False, default="New chat"
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')", name="ck_messages_role"
        ),
        Index("ix_messages_conversation_id", "conversation_id", "id"),
    )

    # Integer autoincrement PK on purpose: it gives messages a strict,
    # portable insertion order (created_at alone has second precision,
    # so two messages in one exchange can share a timestamp).
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


MEMORY_TYPES = (
    "user_preference",
    "personal_fact",
    "project_fact",
    "goal",
    "correction",
    "successful_outcome",
    "failed_outcome",
    "custom",
)

MEMORY_SOURCES = ("manual", "chat_command")


class Memory(Base):
    """One long-term memory. Separate from conversation history.

    * `is_active` implements soft deletion: "forgotten" memories stay in
      the table (auditable, recoverable) but are excluded from listing
      and retrieval by default.
    * `project_id` is a plain nullable UUID for now — the projects table
      (and its FK) arrives with the projects milestone; storing the
      association early keeps this schema stable.
    * No embedding column yet, deliberately: pgvector lands in the next
      part with its own migration and the proper VECTOR type — a dead
      placeholder column now would just be churn.
    """

    __tablename__ = "memories"
    __table_args__ = (
        CheckConstraint(
            "memory_type IN ('user_preference','personal_fact',"
            "'project_fact','goal','correction','successful_outcome',"
            "'failed_outcome','custom')",
            name="ck_memories_type",
        ),
        CheckConstraint(
            "importance_score >= 0 AND importance_score <= 1",
            name="ck_memories_importance",
        ),
        Index("ix_memories_user_active", "user_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    importance_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RegisteredProject(Base):
    """A repository the user explicitly allowed NISH to work with.

    Registration IS the allowlist: coding tools refuse any path that is
    not the resolved root of a registered project owned by the user.
    """

    __tablename__ = "registered_projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    root_path: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    default_branch: Mapped[str] = mapped_column(String(80), nullable=False, default="main")
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
    last_scanned_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CodingTask(Base):
    """One coding request moving through the controlled pipeline."""

    __tablename__ = "coding_tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("registered_projects.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    workspace_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    proposals: Mapped[list["CodingProposal"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    validation_runs: Mapped[list["ValidationRun"]] = relationship(
        back_populates="task", cascade="all, delete-orphan",
        order_by="ValidationRun.id",
    )


class CodingProposal(Base):
    """A generated set of changes, living ONLY in the isolated workspace
    until (a future milestone applies) explicit approval."""

    __tablename__ = "coding_proposals"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("coding_tasks.id", ondelete="CASCADE"), nullable=False
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    diff: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="proposed"
    )  # proposed | approved | rejected
    warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    task: Mapped[CodingTask] = relationship(back_populates="proposals")
    files: Mapped[list["CodingProposalFile"]] = relationship(
        back_populates="proposal", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["Approval"]] = relationship(
        back_populates="proposal", cascade="all, delete-orphan"
    )


class CodingProposalFile(Base):
    """One changed file: original content preserved for rollback/review."""

    __tablename__ = "coding_proposal_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("coding_proposals.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)  # modify|create
    original_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    new_content: Mapped[str] = mapped_column(Text, nullable=False)

    proposal: Mapped[CodingProposal] = relationship(back_populates="files")


class ValidationRun(Base):
    """One allowlisted command executed in the isolated workspace."""

    __tablename__ = "validation_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("coding_tasks.id", ondelete="CASCADE"), nullable=False
    )
    command: Mapped[str] = mapped_column(String(300), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(nullable=True)
    duration_ms: Mapped[int] = mapped_column(nullable=False, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    timed_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    output_excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    task: Mapped[CodingTask] = relationship(back_populates="validation_runs")


class Approval(Base):
    """An explicit user decision on a proposal."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    proposal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("coding_proposals.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # approved|rejected
    note: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    decided_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    proposal: Mapped[CodingProposal] = relationship(back_populates="approvals")


LOCAL_USERNAME = "local"


def get_or_create_local_user(session) -> User:  # type: ignore[no-untyped-def]
    """Return the single local user, creating it on first use.

    This is the stand-in for authentication until the accounts phase.
    The API layer depends on this function alone for "who am I", so
    swapping in real auth later is a one-dependency change.
    """
    from sqlalchemy import select

    user = session.scalar(select(User).where(User.username == LOCAL_USERNAME))
    if user is None:
        user = User(username=LOCAL_USERNAME)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
