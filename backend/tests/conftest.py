"""Shared pytest fixtures.

Fixtures here never construct an Identity with wider access than a real demo user has, and never
provide an unfiltered vector-store client. Every test in this suite runs with no Qdrant, no
PostgreSQL, and no Ollama: anything that would reach a service is faked explicitly, so a test
passing is never evidence that a service happened to be running.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Test configuration must be installed before any app module reads settings.
os.environ.setdefault("AUTH_SECRET", "test-secret-not-a-real-key")
os.environ.setdefault("DEMO_USERS_PATH", str(BACKEND_ROOT / "demo_users.json"))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("JUDGE_CACHE_PATH", str(BACKEND_ROOT / ".pytest_judge_cache.json"))
os.environ.setdefault("EVIDENCE_THRESHOLD", "0.6")
os.environ.setdefault("ADAPTIVE_MAX_ATTEMPTS", "3")
os.environ.setdefault("CHUNK_SIZE_TOKENS", "512")
os.environ.setdefault("CHUNK_OVERLAP_TOKENS", "64")

from app.auth import Identity  # noqa: E402  - must follow the env setup above
from app.ingestion.parsers import ParsedPage  # noqa: E402
from app.retrieval.vector_store import RetrievedChunk  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_caches() -> None:
    """Reset cached settings and judge state between tests."""
    from app.config import reset_settings_cache
    from app.retrieval.scoring import clear_cache

    reset_settings_cache()
    clear_cache()


# --------------------------------------------------------------------------- identities


@pytest.fixture
def hr_identity() -> Identity:
    """A demo HR user at `internal`."""
    return Identity(
        user_id="hr_generalist",
        name="Ayesha Khan",
        department="hr",
        access_level="internal",
        role="HR Generalist",
    )


@pytest.fixture
def hr_director_identity() -> Identity:
    """The same department as hr_identity, one access level up."""
    return Identity(
        user_id="hr_director",
        name="Marta Silva",
        department="hr",
        access_level="confidential",
        role="HR Director",
    )


@pytest.fixture
def engineering_identity() -> Identity:
    """A demo Engineering user with no Finance or HR access."""
    return Identity(
        user_id="eng_ic",
        name="Daniel Osei",
        department="engineering",
        access_level="internal",
        role="Software Engineer",
    )


@pytest.fixture
def finance_identity() -> Identity:
    """A demo Finance user at `confidential`."""
    return Identity(
        user_id="fin_controller",
        name="Priya Raman",
        department="finance",
        access_level="confidential",
        role="Financial Controller",
    )


@pytest.fixture
def all_identities(
    hr_identity: Identity,
    hr_director_identity: Identity,
    engineering_identity: Identity,
    finance_identity: Identity,
) -> list[Identity]:
    """Every demo identity, so a filter test extends automatically when a user is added."""
    return [hr_identity, hr_director_identity, engineering_identity, finance_identity]


# --------------------------------------------------------------------------- corpus doubles


@pytest.fixture
def corpus() -> list[dict]:
    """A small corpus spanning two departments, three access levels, and the org-wide bucket."""
    return [
        {"document_id": "hr-handbook", "department": "all", "access_level": "public"},
        {"document_id": "hr-leave-policy", "department": "hr", "access_level": "internal"},
        {"document_id": "hr-comp-review", "department": "hr", "access_level": "confidential"},
        {"document_id": "fin-procurement", "department": "finance", "access_level": "internal"},
        {
            "document_id": "fin-salary-bands",
            "department": "finance",
            "access_level": "confidential",
        },
        {"document_id": "eng-oncall", "department": "engineering", "access_level": "internal"},
    ]


@pytest.fixture
def make_chunk():  # noqa: ANN201 - factory fixture
    """Build a RetrievedChunk without repeating every field at each call site."""

    def _make(
        document_id: str = "hr-leave-policy",
        text: str = "Employees accrue 20 days of paid annual leave per year.",
        page: int = 2,
        department: str = "hr",
        access_level: str = "internal",
        score: float = 0.82,
        chunk_id: str | None = None,
    ) -> RetrievedChunk:
        return RetrievedChunk(
            chunk_id=chunk_id or f"{document_id}::0000::abcdef123456",
            document_id=document_id,
            text=text,
            page=page,
            department=department,
            access_level=access_level,
            score=score,
        )

    return _make


@pytest.fixture
def make_pages():  # noqa: ANN201 - factory fixture
    """Build ParsedPage lists from plain strings."""

    def _make(*texts: str) -> list[ParsedPage]:
        return [ParsedPage(page=index, text=text) for index, text in enumerate(texts, start=1)]

    return _make


class FakeQdrantClient:
    """A stub Qdrant client that records the filter passed to every search call.

    The access-filter regression test asserts against what this captured. It deliberately has no
    way to search without a filter -- if a caller passes None, the recorded value is None and the
    test fails, which is the whole point.
    """

    def __init__(self, hits: list | None = None) -> None:
        """Start with no recorded calls; `calls` accumulates every search through this."""
        self.hits = hits or []
        self.calls: list[dict] = []

    def query_points(self, **kwargs: object):  # noqa: ANN201
        """Record the call and return the canned hits under a `.points` response shape.

        Mirrors qdrant-client >=1.14, whose `query_points()` returns a response object rather
        than a bare list. The recorded kwargs still carry `query_filter`, so `last_filter` (and
        the access-filter regression test) are unaffected by the API rename.
        """
        self.calls.append(kwargs)
        return SimpleNamespace(points=self.hits)

    @property
    def last_filter(self) -> object:
        """The query_filter from the most recent search call."""
        return self.calls[-1].get("query_filter") if self.calls else None


@pytest.fixture
def fake_vector_store() -> FakeQdrantClient:
    """A Qdrant double that captures search kwargs."""
    return FakeQdrantClient()
