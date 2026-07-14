"""Conversations API — persistent chat.

POST   /api/conversations                    create (optional title)
GET    /api/conversations                    list (newest first)
GET    /api/conversations/{id}               one conversation + messages
PATCH  /api/conversations/{id}               rename
DELETE /api/conversations/{id}               delete (cascades to messages)
POST   /api/conversations/{id}/messages      send a message: persists the
        user message, runs the model over the stored history, persists
        and returns the assistant reply.

The original stateless POST /api/chat is untouched — existing clients
keep working.

Ownership: every query filters by the current user's id. Today "current
user" is the single local user (no auth phase yet); the checks
themselves are real and tested, so the auth phase only swaps the
`current_user` dependency.

Privacy note: message content is stored in the database but deliberately
never written to application logs.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.models import (
    Conversation,
    Message,
    User,
    get_or_create_local_user,
)
from app.database.session import get_db
from app.schemas.conversations import (
    ConversationCreate,
    ConversationDetail,
    ConversationRename,
    ConversationSummary,
    MessageOut,
    SendMessageRequest,
    SendMessageResponse,
)
from app.services.ollama import OllamaError, OllamaService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


def current_user(db: Session = Depends(get_db)) -> User:
    """Stand-in auth dependency — returns the local user."""
    return get_or_create_local_user(db)


def _owned_conversation(
    db: Session, user: User, conversation_id: uuid.UUID
) -> Conversation:
    """Fetch a conversation ONLY if it belongs to the current user.

    A conversation that exists but belongs to someone else returns the
    same 404 as one that doesn't exist — no information leak about other
    users' data.
    """
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@router.post("", response_model=ConversationSummary, status_code=201)
def create_conversation(
    body: ConversationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ConversationSummary:
    conversation = Conversation(
        user_id=user.id, title=body.title or "New chat"
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=0,
    )


@router.get("", response_model=list[ConversationSummary])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[ConversationSummary]:
    rows = db.execute(
        select(Conversation, func.count(Message.id))
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
    ).all()
    return [
        ConversationSummary(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=count,
        )
        for conversation, count in rows
    ]


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Conversation:
    return _owned_conversation(db, user, conversation_id)


@router.patch("/{conversation_id}", response_model=ConversationSummary)
def rename_conversation(
    conversation_id: uuid.UUID,
    body: ConversationRename,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ConversationSummary:
    conversation = _owned_conversation(db, user, conversation_id)
    conversation.title = body.title
    db.commit()
    db.refresh(conversation)
    message_count = db.scalar(
        select(func.count(Message.id)).where(
            Message.conversation_id == conversation.id
        )
    )
    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=message_count or 0,
    )


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    conversation = _owned_conversation(db, user, conversation_id)
    db.delete(conversation)  # messages cascade at the DB level
    db.commit()
    # Deliberately no message content in this log line.
    logger.info("Conversation %s deleted by user %s", conversation_id, user.id)
    return Response(status_code=204)


@router.post(
    "/{conversation_id}/messages", response_model=SendMessageResponse
)
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> SendMessageResponse:
    """Persist the user message, get the model's reply, persist that too.

    The user message is committed BEFORE the model call: if Ollama fails
    or times out, nothing typed is ever lost — the client can retry and
    the history is intact.
    """
    if len(body.content) > settings.max_message_chars:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Message exceeds the maximum length of "
                f"{settings.max_message_chars} characters."
            ),
        )

    conversation = _owned_conversation(db, user, conversation_id)

    user_message = Message(
        conversation_id=conversation.id, role="user", content=body.content
    )
    db.add(user_message)
    # Touch the parent so updated_at moves and list ordering stays fresh.
    conversation.updated_at = func.now()
    db.flush()
    # Auto-title brand-new chats from the first message.
    if conversation.title == "New chat":
        clean = " ".join(body.content.split())
        conversation.title = clean[:57] + "…" if len(clean) > 58 else clean
    db.commit()
    db.refresh(user_message)

    # Build the model context from the STORED history (most recent N).
    history_rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
        .limit(settings.max_history_messages)
    ).all()
    history = [
        {"role": row.role, "content": row.content}
        for row in reversed(history_rows)
    ]

    service = OllamaService(settings)
    try:
        reply_text = await service.chat(history)
    except OllamaError as exc:
        # The user message is already saved; surface a clean error.
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    assistant_message = Message(
        conversation_id=conversation.id, role="assistant", content=reply_text
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    return SendMessageResponse(
        user_message=MessageOut.model_validate(user_message),
        assistant_message=MessageOut.model_validate(assistant_message),
        model=service.model,
    )
