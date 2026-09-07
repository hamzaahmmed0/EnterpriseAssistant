"""Qdrant client wrapper: collection lifecycle, payload schema, and filtered search.

Every search that leaves this module carries a filter. There is no unfiltered search function
here, and none may be added -- not for tests, not for debugging, not temporarily.
"""

from dataclasses import dataclass
from typing import Any


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


def ensure_collection(collection: str, vector_size: int) -> None:
    """Create the collection if absent and verify its vector size matches the embedding model.

    Args:
        collection: Qdrant collection name.
        vector_size: settings.embedding_dim.

    Raises:
        VectorStoreError: If the collection exists with a different vector size.
    """
    raise NotImplementedError


def upsert_chunks(collection: str, points: list[dict[str, Any]]) -> int:
    """Upsert embedded chunks into a collection.

    Args:
        collection: Target collection.
        points: Points carrying vector and payload. Every payload must include document_id,
            department, access_level, and page.

    Returns:
        Number of points written.

    Raises:
        VectorStoreError: If any payload is missing a required access-control field.
    """
    raise NotImplementedError


def search(
    collection: str,
    query_vector: list[float],
    qdrant_filter: dict[str, Any],
    top_k: int,
) -> list[RetrievedChunk]:
    """Run a pre-filtered vector search.

    Args:
        collection: Collection to search.
        query_vector: Embedded query.
        qdrant_filter: Filter from build_access_filter. Required, never optional.
        top_k: Number of chunks to return -- k authorized chunks, since filtering is native.
    """
    raise NotImplementedError


class VectorStoreError(Exception):
    """Raised on collection or payload contract violations."""


# TODO:
#  1. Define the payload schema constant (document_id, department, access_level, page, chunk_index)
#     and validate against it inside upsert_chunks -- assert at ingest, do not trust callers.
#  2. Implement ensure_collection() with the vector-size assertion; a silent mismatch here
#     invalidates every retrieval number in docs/EVALUATION.md.
#  3. Create Qdrant payload indexes on department and access_level so the pre-filter is cheap.
#  4. Implement upsert_chunks() with deterministic point ids so re-ingest is idempotent.
#  5. Implement search(): call assert_filter_non_empty(), then pass the filter into the query --
#     never post-process the result list.
#  6. Emit log_access_decision() from search() with the serialised filter and the result count.
#  7. Add the collection bootstrap CLI used in README setup step 6.
