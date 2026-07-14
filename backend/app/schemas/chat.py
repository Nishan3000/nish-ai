"""Request/response schemas for the chat endpoint.

Validation happens here, at the edge, so nothing malformed ever reaches
the service layer. Limits (message length, history size) are enforced in
the API route using values from Settings, because Pydantic field
constraints must be static.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.memories import MemoryUsed

# Only these roles are accepted from the client. "system" is intentionally
# excluded: the system prompt is owned by the backend, so a client cannot
# inject or override it. (This is our first, small prompt-injection guard.)
ClientRole = Literal["user", "assistant"]


class ChatMessage(BaseModel):
    """A single message in the conversation history."""

    role: ClientRole
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    """Body of POST /api/chat."""

    messages: list[ChatMessage] = Field(min_length=1)


class ChatResponse(BaseModel):
    """Successful reply from POST /api/chat."""

    reply: str
    model: str
    # Long-term memories injected into this response's context (empty when
    # none were relevant). Additive field: older clients simply ignore it.
    memories_used: list[MemoryUsed] = []


class HealthResponse(BaseModel):
    """Body of GET /api/health."""

    status: Literal["ok"]
    app: str
    ollama: Literal["reachable", "unreachable"]
    ollama_model: str
