"""PostgreSQL engine and session lifecycle.

PostgreSQL is the source of truth for document metadata; Qdrant payloads are a derived copy
(ADR-008). Ingestion writes both or neither.
"""

from collections.abc import Iterator

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def create_engine_from_settings() -> Engine:
    """Build the SQLAlchemy engine from settings.database_url."""
    raise NotImplementedError


def get_session() -> Iterator[Session]:
    """Yield a scoped database session, committing on success and rolling back on error."""
    raise NotImplementedError


def init_schema() -> None:
    """Create the schema if it does not exist."""
    raise NotImplementedError


# TODO:
#  1. Resolve ADR-008 (Alembic vs. create_all) before implementing init_schema().
#  2. Implement create_engine_from_settings() with pool sizing suitable for a single VM.
#  3. Implement get_session() as a FastAPI dependency-compatible generator.
#  4. Add a documented reset command (drop + recreate) for the demo, since the schema will churn.
