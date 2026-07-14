"""Public identity endpoint.

GET /api/identity returns who NISH is: name, tagline, creator, version,
purpose, personality, and the CURRENT language model (read live from
configuration, so a model change is reported automatically).

Only public fields leave this endpoint — no file paths, no environment
variables, no secrets. A broken identity file returns a clean 503.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.core.identity import IdentityConfigError, get_identity_manager

router = APIRouter(tags=["identity"])


@router.get("/identity")
async def identity(settings: Settings = Depends(get_settings)) -> dict:
    try:
        manager = get_identity_manager()
    except IdentityConfigError as exc:
        # Human-readable reason, but never internal paths beyond the
        # expected filename the message already limits itself to.
        raise HTTPException(status_code=503, detail=str(exc))
    return manager.public_info(current_model=settings.ollama_model)
