"""Nova AI backend — application entrypoint.

Run in development with:
    uvicorn app.main:app --reload --port 8000
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, chat, health
from app.core.config import get_settings

# Basic structured-ish logging; replaced by proper log config in Phase 9.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
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
