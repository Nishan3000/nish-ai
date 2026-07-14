"""Schemas for the conversations API.

Same philosophy as the chat schemas: validation at the edge, and clients
can never supply a role — the server decides what is 'user' and what is
'assistant', so the stored history cannot be forged via the API.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.memories import MemoryUsed


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut]


class SendMessageRequest(BaseModel):
    """Body of POST /api/conversations/{id}/messages."""

    content: str = Field(min_length=1)


class SendMessageResponse(BaseModel):
    """The persisted exchange."""

    user_message: MessageOut
    assistant_message: MessageOut
    model: str
    # Long-term memories injected into this response's context (empty when
    # none were relevant). Additive field: older clients simply ignore it.
    memories_used: list[MemoryUsed] = []
