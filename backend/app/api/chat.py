"""Chat endpoint.

POST /api/chat receives the conversation history from the frontend,
validates it, forwards it to Ollama, and returns the reply.

In Phase 1 the frontend keeps the history in browser memory and sends it
with every request (the backend is stateless). Phase 2 moves history into
PostgreSQL.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.ollama import OllamaError, OllamaService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    settings: Settings = Depends(get_settings),
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

    service = OllamaService(settings)
    try:
        reply = await service.chat(
            [m.model_dump() for m in request.messages]
        )
    except OllamaError as exc:
        # Map service errors to clean HTTP errors; never leak stack traces.
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return ChatResponse(reply=reply, model=service.model)
