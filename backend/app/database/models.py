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
