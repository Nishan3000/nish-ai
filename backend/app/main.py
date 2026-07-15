"""NISH backend — application entrypoint.

Run in development with:
    uvicorn app.main:app --reload --port 8000
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.exc import OperationalError

from app.api import agent, chat, coding, conversations, health, identity, memories
from app.core.config import get_settings

# Basic structured-ish logging; replaced by proper log config in Phase 9.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = get_settings()

# Application version comes from the identity configuration; fall back
# quietly so a broken identity file cannot prevent startup (the
# /api/identity endpoint reports the problem in detail).
try:
    from app.core.identity import get_identity_manager

    _app_version = get_identity_manager().identity.version
except Exception:  # noqa: BLE001 — deliberate graceful degradation
    _app_version = "0.0.0"

app = FastAPI(
    title=settings.app_name,
    version=_app_version,
    # Interactive docs are handy in development; we lock these down
    # (or disable them) when we harden for production in Phase 9.
    docs_url="/docs",
    redoc_url=None,
)

# CORS: only the origins listed in the CORS_ORIGINS env var may call this
# API from a browser. Credentials stay disabled until auth lands in Phase 2.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(agent.router, prefix=settings.api_prefix)
app.include_router(conversations.router, prefix=settings.api_prefix)
app.include_router(identity.router, prefix=settings.api_prefix)
app.include_router(memories.router, prefix=settings.api_prefix)
app.include_router(coding.router, prefix=settings.api_prefix)


@app.exception_handler(OperationalError)
async def database_unavailable(_request, _exc: OperationalError):
    """Clean 503 instead of a stack trace when PostgreSQL is down."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Database unavailable. Is PostgreSQL running? "
                "Start it with: docker compose up db"
            )
        },
    )
