"""PostgreSQL engine and session lifecycle.

PostgreSQL is the source of truth for document metadata; Qdrant payloads are a derived copy
(ADR-008). Ingestion writes both or neither.

Schema management is ``create_all`` plus a documented reset, not Alembic: the schema churns
weekly for four weeks and there is no production database to migrate.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Base


@lru_cache
def get_engine() -> Engine:
    """Build (once) the SQLAlchemy engine from settings.database_url."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Process-wide session factory."""
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def reset_engine_cache() -> None:
    """Dispose the engine and clear caches. Shutdown and tests only."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on error, always close."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session bound to the request."""
    with session_scope() as session:
        yield session


def init_schema() -> None:
    """Create every table that does not yet exist."""
    Base.metadata.create_all(bind=get_engine())


def reset_schema() -> None:
    """Drop and recreate the schema.

    The documented reset path for a demo with synthetic data (ADR-008). Destructive: it deletes
    every conversation, review, and document row. Vector data in Qdrant is untouched, so a reset
    should be followed by a re-ingest to keep the two stores consistent.
    """
    Base.metadata.drop_all(bind=get_engine())
    Base.metadata.create_all(bind=get_engine())


def health() -> dict[str, object]:
    """Report whether PostgreSQL is reachable."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"reachable": True}
    except Exception as exc:  # noqa: BLE001 - health checks report, never raise
        return {"reachable": False, "error": str(exc)}
