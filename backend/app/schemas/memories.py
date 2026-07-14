"""Schemas for the memories API."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MemoryType = Literal[
    "user_preference",
    "personal_fact",
    "project_fact",
    "goal",
    "correction",
    "successful_outcome",
    "failed_outcome",
    "custom",
]


class MemoryCreate(BaseModel):
    memory_type: MemoryType
    content: str = Field(min_length=3)
    importance_score: float = Field(default=0.5, ge=0, le=1)
    project_id: uuid.UUID | None = None


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=3)
    memory_type: MemoryType | None = None
    importance_score: float | None = Field(default=None, ge=0, le=1)
    is_active: bool | None = None


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    memory_type: str
    content: str
    source: str
    importance_score: float
    is_active: bool
    project_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class MemoryUsed(BaseModel):
    """Compact form attached to chat responses ('memories used')."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    memory_type: str
    content: str


class ClearAllResponse(BaseModel):
    cleared: int
