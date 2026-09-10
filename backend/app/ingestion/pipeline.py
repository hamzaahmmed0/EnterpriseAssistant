"""Ingestion orchestration: corpus directory in, populated Qdrant and PostgreSQL out.

Writes both stores or neither (ADR-008), refuses to write a chunk without access tags, and
audits the collections afterwards so an untagged point fails the run rather than sitting in the
index as a hole in the access boundary.

CLI::

    python -m app.ingestion.pipeline --manifest data/corpus/manifest.json
    python -m app.ingestion.pipeline --manifest ... --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings
from app.db import init_schema, session_scope
from app.ingestion.chunking import Chunk, chunk_pages
from app.ingestion.embedder import embed_texts, embedding_dimension
from app.ingestion.parsers import parse_document
from app.models import Document
from app.observability import configure_logging, log_error
from app.retrieval.access_filter import ACCESS_LEVEL_ORDER
from app.retrieval.vector_store import (
    VectorStoreError,
    audit_payload_tags,
    count_points,
    ensure_collection,
    upsert_chunks,
)

#: Manifest `collection` values and the Qdrant collections each routes to (ADR-007).
COLLECTION_ROUTES = {"documents", "policy", "both"}


class ManifestError(Exception):
    """Raised when the corpus manifest is missing, malformed, or untagged."""


@dataclass(frozen=True)
class DocumentSpec:
    """A source document and the access tags it must be ingested with."""

    document_id: str
    title: str
    path: str
    department: str
    access_level: str
    collection: str = "documents"
    injection_test: bool = False


@dataclass
class IngestReport:
    """What one ingestion run did, for the eval provenance block."""

    documents: int = 0
    chunks: int = 0
    skipped: list[str] = field(default_factory=list)
    collection_counts: dict[str, int] = field(default_factory=dict)
    corpus_hash: str = ""
    injection_test_documents: int = 0

    def as_dict(self) -> dict:
        """Serialisable form, written next to eval results."""
        return {
            "documents": self.documents,
            "chunks": self.chunks,
            "skipped": self.skipped,
            "collection_counts": self.collection_counts,
            "corpus_hash": self.corpus_hash,
            "injection_test_documents": self.injection_test_documents,
        }


def load_manifest(path: str | None = None) -> list[DocumentSpec]:
    """Read the corpus manifest describing each document and its access tags.

    The manifest is the only place access tags come from -- never a filename, never a folder
    name (ADR-001). Expected shape::

        [
          {
            "document_id": "hr-leave-policy-v3",
            "title": "Annual Leave Policy",
            "path": "hr/leave-policy-v3.pdf",
            "department": "hr",
            "access_level": "internal",
            "collection": "documents",
            "injection_test": false
          }
        ]

    ``path`` is relative to settings.ingest_source_dir. ``collection`` is one of
    ``documents`` | ``policy`` | ``both``.

    Raises:
        ManifestError: If the file is missing/malformed, or any entry lacks a department, an
            access level, or uses an unknown value for either.
    """
    settings = get_settings()
    resolved = Path(path or settings.ingest_manifest_path)
    if not resolved.exists():
        raise ManifestError(
            f"manifest not found: {resolved}. Author it alongside the corpus "
            "(docs/PLAN.md task 1.1)."
        )

    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(raw, list) or not raw:
        raise ManifestError("manifest must be a non-empty JSON array")

    specs: list[DocumentSpec] = []
    seen_ids: set[str] = set()
    for entry in raw:
        for required in ("document_id", "title", "path", "department", "access_level"):
            if not entry.get(required):
                raise ManifestError(
                    f"manifest entry {entry.get('document_id', '<unknown>')} is missing "
                    f"{required!r}"
                )

        department = str(entry["department"]).strip().lower()
        access_level = str(entry["access_level"]).strip().lower()
        collection = str(entry.get("collection", "documents")).strip().lower()

        if access_level not in ACCESS_LEVEL_ORDER:
            raise ManifestError(
                f"{entry['document_id']}: unknown access_level {access_level!r}; expected one of "
                f"{sorted(ACCESS_LEVEL_ORDER)}"
            )
        if collection not in COLLECTION_ROUTES:
            raise ManifestError(
                f"{entry['document_id']}: unknown collection {collection!r}; expected one of "
                f"{sorted(COLLECTION_ROUTES)}"
            )
        if entry["document_id"] in seen_ids:
            raise ManifestError(f"duplicate document_id {entry['document_id']!r} in manifest")
        seen_ids.add(entry["document_id"])

        specs.append(
            DocumentSpec(
                document_id=str(entry["document_id"]),
                title=str(entry["title"]),
                path=str(entry["path"]),
                department=department,
                access_level=access_level,
                collection=collection,
                injection_test=bool(entry.get("injection_test", False)),
            )
        )
    return specs


def _target_collections(spec: DocumentSpec) -> list[str]:
    """Resolve a manifest routing value to concrete Qdrant collection names (ADR-007)."""
    settings = get_settings()
    if spec.collection == "documents":
        return [settings.qdrant_documents_collection]
    if spec.collection == "policy":
        return [settings.qdrant_policy_collection]
    return [settings.qdrant_documents_collection, settings.qdrant_policy_collection]


def chunks_for(spec: DocumentSpec) -> tuple[list[Chunk], int]:
    """Parse and chunk one document. Returns its chunks and its page count."""
    settings = get_settings()
    source = Path(settings.ingest_source_dir) / spec.path
    pages = parse_document(source)
    chunks = chunk_pages(
        pages=pages,
        document_id=spec.document_id,
        department=spec.department,
        access_level=spec.access_level,
        chunk_size=settings.chunk_size_tokens,
        overlap=settings.chunk_overlap_tokens,
    )
    return chunks, len(pages)


def ingest_document(spec: DocumentSpec) -> int:
    """Parse, clean, chunk, embed, and upsert one document; write its row. Returns chunk count.

    The Qdrant upsert and the PostgreSQL row are written in one unit of work: if the row fails,
    the transaction rolls back and the run aborts rather than leaving the two stores disagreeing.
    """
    chunks, page_count = chunks_for(spec)
    if not chunks:
        raise ValueError(f"{spec.document_id}: parsed to zero chunks; check the source file")

    vectors = embed_texts([chunk.text for chunk in chunks])
    points = [
        {
            "chunk_id": chunk.chunk_id,
            "vector": vector,
            "payload": {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "page": chunk.page,
                "department": chunk.department,
                "access_level": chunk.access_level,
            },
        }
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]

    with session_scope() as session:
        for collection in _target_collections(spec):
            upsert_chunks(collection, points)
        session.merge(
            Document(
                id=spec.document_id,
                title=spec.title,
                department=spec.department,
                access_level=spec.access_level,
                source_path=spec.path,
                collection=spec.collection,
                page_count=page_count,
                chunk_count=len(chunks),
                injection_test=spec.injection_test,
            )
        )

    return len(chunks)


def corpus_hash(specs: list[DocumentSpec]) -> str:
    """Hash the corpus contents, so a results file can prove which corpus produced it."""
    digest = hashlib.sha256()
    source_dir = Path(get_settings().ingest_source_dir)
    for spec in sorted(specs, key=lambda item: item.document_id):
        digest.update(spec.document_id.encode())
        digest.update(spec.department.encode())
        digest.update(spec.access_level.encode())
        path = source_dir / spec.path
        if path.exists():
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()[:16]


def ingest_corpus(manifest_path: str | None = None, *, dry_run: bool = False) -> IngestReport:
    """Ingest every document in the manifest into its target collection(s).

    Args:
        manifest_path: Manifest to read. Defaults to settings.ingest_manifest_path.
        dry_run: Parse, chunk, and validate without embedding or writing anything.

    Raises:
        VectorStoreError: If any point in either collection lacks an access tag after the run.
    """
    settings = get_settings()
    specs = load_manifest(manifest_path)
    report = IngestReport(corpus_hash=corpus_hash(specs))
    report.injection_test_documents = sum(1 for spec in specs if spec.injection_test)

    if dry_run:
        for spec in specs:
            try:
                chunks, _ = chunks_for(spec)
                report.documents += 1
                report.chunks += len(chunks)
            except Exception as exc:  # noqa: BLE001 - dry run reports every problem at once
                report.skipped.append(f"{spec.document_id}: {exc}")
        return report

    init_schema()
    dimension = embedding_dimension()
    if dimension != settings.embedding_dim:
        raise VectorStoreError(
            f"{settings.embedding_model} produces {dimension}-dimension vectors but "
            f"EMBEDDING_DIM is {settings.embedding_dim}"
        )
    for collection in (settings.qdrant_documents_collection, settings.qdrant_policy_collection):
        ensure_collection(collection, settings.embedding_dim)

    for spec in specs:
        try:
            report.chunks += ingest_document(spec)
            report.documents += 1
        except Exception as exc:  # noqa: BLE001 - one bad document must not abort the corpus
            log_error("ingest_failed", document_id=spec.document_id, error=str(exc))
            report.skipped.append(f"{spec.document_id}: {exc}")

    for collection in (settings.qdrant_documents_collection, settings.qdrant_policy_collection):
        untagged = audit_payload_tags(collection)
        if untagged:
            raise VectorStoreError(
                f"{len(untagged)} point(s) in {collection} have no department/access_level: "
                f"{untagged[:5]}. That is a hole in the access boundary -- fix and re-ingest."
            )
        report.collection_counts[collection] = count_points(collection)

    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Ingest the corpus into Qdrant and PostgreSQL.")
    parser.add_argument("--manifest", default=None, help="Path to the corpus manifest JSON.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and chunk without embedding or writing. Use this before a real run.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)

    report = ingest_corpus(args.manifest, dry_run=args.dry_run)
    print(json.dumps(report.as_dict(), indent=2))

    if report.skipped:
        print(f"\n{len(report.skipped)} document(s) skipped.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
