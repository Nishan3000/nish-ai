"""Database engine and session management.

Synchronous SQLAlchemy 2.0 on purpose: FastAPI runs sync dependencies in
a threadpool, the app is single-user/local, and sync keeps the code (and
Alembic setup) simple and understandable — one of NISH's stated goals.

Connection details come from DATABASE_URL (see core/config.py); nothing
is hard-coded. Tests override `get_db` with their own engine.
"""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """One engine per process. pool_pre_ping survives DB restarts."""
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
