"""Fixed-size chunking with overlap (ADR-003).

Chunk size and overlap come from config so they can be swept during calibration. Page provenance
is carried through, because citations and recall@5 both depend on it.
"""

from dataclasses import dataclass

from app.ingestion.parsers import ParsedPage


@dataclass(frozen=True)
class Chunk:
    """A unit of text as stored in Qdrant, with everything a citation and a filter need."""

    chunk_id: str
    document_id: str
    chunk_index: int
    text: str
    page: int
    department: str
    access_level: str


def chunk_pages(
    pages: list[ParsedPage],
    document_id: str,
    department: str,
    access_level: str,
    chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    """Split parsed pages into overlapping chunks tagged with access control metadata.

    Args:
        pages: Cleaned pages in document order.
        document_id: Stable id used in citations and the eval datasets.
        department: Owning department; becomes a Qdrant payload field.
        access_level: Required access level; becomes a Qdrant payload field.
        chunk_size: settings.chunk_size_tokens.
        overlap: settings.chunk_overlap_tokens.

    Raises:
        ValueError: If overlap >= chunk_size, or if department or access_level is empty.
    """
    raise NotImplementedError


def count_tokens(text: str) -> int:
    """Return the token count used to measure chunk size."""
    raise NotImplementedError


# TODO:
#  1. Resolve ADR-003 (chunk size, overlap, and whether size is tokens or characters) and record
#     the chosen values before implementing chunk_pages().
#  2. Implement count_tokens() against the tokenizer named in that decision; do not approximate.
#  3. Implement chunk_pages() so a chunk spanning a page boundary is attributed to the page where
#     it starts, and write that rule into the docstring once chosen.
#  4. Raise on empty department or access_level -- an untagged chunk must be unconstructable.
#  5. Test: exact boundary behaviour at chunk_size, at chunk_size + 1, and at overlap - 1.
#  6. Test: a document shorter than chunk_size produces exactly one chunk with the right page.
#  7. Test: overlap actually overlaps, by asserting the shared substring between consecutive
#     chunks.
#  8. Test: chunk_ids are deterministic across runs, so re-ingest is idempotent.
