"""Ingestion orchestration: corpus directory in, populated Qdrant and PostgreSQL out.

Writes both stores or neither (ADR-008), and refuses to write a chunk without access tags.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentSpec:
    """A source document and the access tags it must be ingested with."""

    document_id: str
    title: str
    path: str
    department: str
    access_level: str
    collection: str


@dataclass(frozen=True)
class IngestReport:
    """What one ingestion run did, for the eval provenance block."""

    documents: int
    chunks: int
    skipped: list[str]
    collection_counts: dict[str, int]


def load_manifest(path: str) -> list[DocumentSpec]:
    """Read the corpus manifest describing each document and its access tags."""
    raise NotImplementedError


def ingest_document(spec: DocumentSpec) -> int:
    """Parse, clean, chunk, embed, and upsert one document. Returns the chunk count."""
    raise NotImplementedError


def ingest_corpus(manifest_path: str) -> IngestReport:
    """Ingest every document in the manifest into its target collection."""
    raise NotImplementedError


def main() -> None:
    """CLI entrypoint: python -m app.ingestion.pipeline --manifest <path>."""
    raise NotImplementedError


# TODO:
#  1. Define the corpus manifest format (JSON) and author it alongside the synthetic corpus in
#     Sprint 1 task 1.1; access tags belong in the manifest, never inferred from a filename.
#  2. Implement load_manifest() with a hard failure on a missing department or access_level.
#  3. Implement ingest_document(): parse -> clean -> chunk -> embed -> upsert, and write the
#     documents row in PostgreSQL in the same unit of work.
#  4. Implement ingest_corpus() and make re-ingest idempotent via deterministic chunk ids.
#  5. Route policy documents into policy_collection as well as documents_collection, per ADR-007,
#     and make the routing explicit in the manifest rather than implicit in code.
#  6. After ingest, assert that every point in both collections has non-null department and
#     access_level; fail the run on any violation rather than warning.
#  7. Emit an IngestReport with a corpus hash for the eval provenance block.
#  8. Implement main() with argparse; document it as README setup step 7.
