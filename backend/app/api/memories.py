"""Memories API.

GET    /api/memories                list/search/filter (active by default)
POST   /api/memories                create (source='manual')
PATCH  /api/memories/{id}           edit content/type/importance/is_active
DELETE /api/memories/{id}           soft delete
DELETE /api/memories?confirm=true   soft-delete ALL (explicit confirmation)

Ownership is enforced in the service layer: foreign memories 404.
All create/update/delete/retrieve operations emit audit events.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.conversations import current_user
from app.database.models import User
from app.database.session import get_db
from app.schemas.memories import (
    ClearAllResponse,
    MemoryCreate,
    MemoryOut,
    MemoryUpdate,
)
from app.services import memory as memory_service

router = APIRouter(prefix="/memories", tags=["memories"])


@router.get("", response_model=list[MemoryOut])
def list_memories(
    memory_type: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=200),
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[MemoryOut]:
    memories = memory_service.list_memories(
        db,
        user,
        memory_type=memory_type,
        query=q,
        include_inactive=include_inactive,
    )
    return [MemoryOut.model_validate(memory) for memory in memories]


@router.post("", response_model=MemoryOut, status_code=201)
def create_memory(
    body: MemoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> MemoryOut:
    memory = memory_service.create_memory(
        db,
        user,
        memory_type=body.memory_type,
        content=body.content,
        source="manual",
        importance_score=body.importance_score,
        project_id=body.project_id,
    )
    return MemoryOut.model_validate(memory)


@router.patch("/{memory_id}", response_model=MemoryOut)
def update_memory(
    memory_id: uuid.UUID,
    body: MemoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> MemoryOut:
    memory = memory_service.update_memory(
        db,
        user,
        memory_id,
        content=body.content,
        memory_type=body.memory_type,
        importance_score=body.importance_score,
        is_active=body.is_active,
    )
    return MemoryOut.model_validate(memory)


@router.delete("/{memory_id}", status_code=204)
def delete_memory(
    memory_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    memory_service.soft_delete_memory(db, user, memory_id)
    return Response(status_code=204)


@router.delete("", response_model=ClearAllResponse)
def clear_all(
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ClearAllResponse:
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                "Deleting all memories requires explicit confirmation: "
                "add ?confirm=true."
            ),
        )
    return ClearAllResponse(cleared=memory_service.clear_all_memories(db, user))
