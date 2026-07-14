"""Chat endpoint.

POST /api/chat receives the conversation history from the frontend,
validates it, forwards it to Ollama, and returns the reply.

In Phase 1 the frontend keeps the history in browser memory and sends it
with every request (the backend is stateless). Phase 2 moves history into
PostgreSQL.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.memories import MemoryUsed
from app.database.session import get_db
from app.services import memory as memory_service
from app.services.ollama import OllamaError, OllamaService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Send the conversation to the local model and return its reply."""

    # --- Input limits (schema validates shape; these validate size) ---
    if len(request.messages) > settings.max_history_messages:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Too many messages in one request "
                f"(max {settings.max_history_messages})."
            ),
        )
    for message in request.messages:
        if len(message.content) > settings.max_message_chars:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"A message exceeds the maximum length of "
                    f"{settings.max_message_chars} characters."
                ),
            )

    # Long-term memory: explicit commands and retrieval, both optional.
    # This endpoint predates the database and must keep working without
    # one, so ALL memory operations degrade gracefully on DB errors.
    latest = request.messages[-1].content
    retrieved: list = []
    memory_context: str | None = None
    try:
        from app.database.models import get_or_create_local_user

        user = get_or_create_local_user(db)
        command = memory_service.handle_memory_command(db, user, latest)
        if command is not None:
            return ChatResponse(reply=command.reply, model=settings.ollama_model)
        retrieved = memory_service.retrieve_relevant(db, user, latest)
        if retrieved:
            memory_context = memory_service.build_memory_context(retrieved)
    except SQLAlchemyError:
        logger.warning(
            "Database unavailable — chat continues without long-term memory."
        )

    service = OllamaService(settings)
    try:
        reply = await service.chat(
            [m.model_dump() for m in request.messages],
            memory_context=memory_context,
        )
    except OllamaError as exc:
        # Map service errors to clean HTTP errors; never leak stack traces.
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return ChatResponse(
        reply=reply,
        model=service.model,
        memories_used=[MemoryUsed.model_validate(m) for m in retrieved],
    )
