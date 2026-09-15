"""Qdrant client wrapper: collection lifecycle, payload schema, and filtered search.

Every search that leaves this module carries a filter. There is no unfiltered search function
here, and none may be added -- not for tests, not for debugging, not temporarily. The regression
test in backend/tests/test_access_filter.py fails if one appears.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.auth import Identity
from app.config import get_settings
from app.observability import log_access_decision
from app.retrieval.access_filter import assert_filter_non_empty

#: Payload fields every point must carry. Asserted at ingest, never assumed at search.
REQUIRED_PAYLOAD_FIELDS = ("document_id", "department", "access_level", "page", "chunk_index")

#: Payload fields the access filter matches on, and which therefore need a Qdrant index.
INDEXED_PAYLOAD_FIELDS = ("department", "access_level", "document_id")


class VectorStoreError(Exception):
    """Raised on collection or payload contract violations."""


@dataclass(frozen=True)
class RetrievedChunk:
    """One chunk returned by a filtered search, with the metadata a citation needs."""

    chunk_id: str
    document_id: str
    text: str
    page: int
    department: str
    access_level: str
    score: float


@lru_cache
def get_client():  # noqa: ANN201 - QdrantClient type imported lazily
    """Process-wide Qdrant client."""
    from qdrant_client import QdrantClient

    settings = get_settings()
    return QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        api_key=settings.qdrant_api_key or None,
    )


def reset_client_cache() -> None:
    """Drop the cached client. Tests and shutdown only."""
    get_client.cache_clear()


def ensure_collection(collection: str, vector_size: int) -> None:
    """Create the collection if absent and verify its vector size matches the embedding model.

    Args:
        collection: Qdrant collection name.
        vector_size: settings.embedding_dim.

    Raises:
        VectorStoreError: If the collection exists with a different vector size. A silent
            mismatch here invalidates every retrieval number in docs/EVALUATION.md.
    """
    from qdrant_client import models

    client = get_client()

    if client.collection_exists(collection):
        info = client.get_collection(collection)
        params = info.config.params.vectors
        existing = params.size if hasattr(params, "size") else None
        if existing is not None and existing != vector_size:
            raise VectorStoreError(
                f"collection {collection!r} has vector size {existing}, but EMBEDDING_DIM is "
                f"{vector_size}. Re-create the collection or fix .env -- do not ingest into it."
            )
    else:
        client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )

    for field in INDEXED_PAYLOAD_FIELDS:
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        except Exception:  # noqa: BLE001 - index already exists is the common, benign case
            continue


def _point_id(chunk_id: str) -> str:
    """Map a deterministic chunk id onto a Qdrant point id (UUIDv5), keeping ingest idempotent."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def upsert_chunks(collection: str, points: list[dict[str, Any]]) -> int:
    """Upsert embedded chunks into a collection.

    Args:
        collection: Target collection.
        points: Each ``{"chunk_id": str, "vector": list[float], "payload": dict}``. Every payload
            must include every field in REQUIRED_PAYLOAD_FIELDS.

    Returns:
        Number of points written.

    Raises:
        VectorStoreError: If any payload is missing a required access-control field. Assert at
            ingest; never trust a caller to have tagged its own chunks.
    """
    from qdrant_client import models

    if not points:
        return 0

    structs = []
    for point in points:
        payload = point.get("payload") or {}
        missing = [field for field in REQUIRED_PAYLOAD_FIELDS if payload.get(field) in (None, "")]
        if missing:
            raise VectorStoreError(
                f"chunk {point.get('chunk_id', '<unknown>')} is missing payload fields: "
                f"{', '.join(missing)}. Refusing to ingest an untagged chunk."
            )
        structs.append(
            models.PointStruct(
                id=_point_id(point["chunk_id"]),
                vector=point["vector"],
                payload=payload,
            )
        )

    get_client().upsert(collection_name=collection, points=structs, wait=True)
    return len(structs)


def search(
    collection: str,
    query_vector: list[float],
    qdrant_filter: dict[str, Any],
    top_k: int,
    identity: Identity,
    score_floor: float | None = None,
) -> list[RetrievedChunk]:
    """Run a pre-filtered vector search.

    Args:
        collection: Collection to search.
        query_vector: Embedded query.
        qdrant_filter: Filter from build_access_filter. Required, never optional.
        top_k: Number of chunks to return -- k *authorized* chunks, since filtering is native.
        identity: Caller, for the access-decision log. Passing it here means a search cannot be
            made without an identity even by accident.
        score_floor: Optional per-chunk similarity floor.

    Returns:
        Chunks ordered by descending score.

    Raises:
        AccessFilterError: If the filter is empty or missing a required condition.
    """
    from qdrant_client import models

    assert_filter_non_empty(qdrant_filter)

    # qdrant-client >=1.14 removed the deprecated `.search()`; `.query_points()` is the current
    # entry point and its server API exists from Qdrant 1.10 onward. It returns a response object
    # whose `.points` are the ScoredPoints (same `.payload`/`.score`/`.id` shape as before).
    response = get_client().query_points(
        collection_name=collection,
        query=query_vector,
        query_filter=models.Filter(**qdrant_filter),
        limit=top_k,
        score_threshold=score_floor,
        with_payload=True,
    )
    hits = getattr(response, "points", response)

    chunks = [
        RetrievedChunk(
            chunk_id=hit.payload.get("chunk_id", str(hit.id)),
            document_id=hit.payload["document_id"],
            text=hit.payload.get("text", ""),
            page=int(hit.payload.get("page", 0)),
            department=hit.payload["department"],
            access_level=hit.payload["access_level"],
            score=float(hit.score),
        )
        for hit in hits
    ]

    log_access_decision(
        user_id=identity.user_id,
        department=identity.department,
        access_level=identity.access_level,
        applied_filter=qdrant_filter,
        collection=collection,
        outcome="allow" if chunks else "deny",
        result_count=len(chunks),
    )
    return chunks


def count_points(collection: str) -> int:
    """Total points in a collection. Used by the ingest report and the startup health check."""
    return int(get_client().count(collection_name=collection, exact=True).count)


def audit_payload_tags(collection: str, batch: int = 256) -> list[str]:
    """Scan a collection and return the ids of any point missing an access tag.

    Ingestion calls this after a run and fails on any violation rather than warning: a single
    untagged chunk is a hole in the access boundary, not a data-quality nit.
    """
    client = get_client()
    offending: list[str] = []
    offset = None

    while True:
        records, offset = client.scroll(
            collection_name=collection,
            limit=batch,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for record in records:
            payload = record.payload or {}
            if not payload.get("department") or not payload.get("access_level"):
                offending.append(str(record.id))
        if offset is None:
            break

    return offending
