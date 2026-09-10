"""Fixed-size chunking with overlap (ADR-003).

Chunk size and overlap come from config so they can be swept during calibration. Size is measured
in tiktoken cl100k_base tokens, used purely as a stable measuring stick -- explicitly not the
embedding model's own tokenizer, which Ollama does not expose.

Page provenance is carried through: a chunk spanning a page boundary is attributed to the page
where it starts (ADR-012), because that is what a citation should point a reader at.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache

from app.ingestion.parsers import ParsedPage

TOKENIZER_NAME = "cl100k_base"


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


@lru_cache
def _encoding():  # noqa: ANN202 - tiktoken's Encoding type is not worth importing eagerly
    """Load and cache the measuring tokenizer."""
    import tiktoken

    return tiktoken.get_encoding(TOKENIZER_NAME)


def count_tokens(text: str) -> int:
    """Return the token count used to measure chunk size (ADR-003)."""
    if not text:
        return 0
    return len(_encoding().encode(text))


def make_chunk_id(document_id: str, chunk_index: int, text: str) -> str:
    """Deterministic chunk id, so re-ingesting the same corpus is idempotent (ADR-008)."""
    digest = hashlib.sha256(f"{document_id}:{chunk_index}:{text}".encode()).hexdigest()
    return f"{document_id}::{chunk_index:04d}::{digest[:12]}"


def chunk_pages(
    pages: list[ParsedPage],
    document_id: str,
    department: str,
    access_level: str,
    chunk_size: int,
    overlap: int,
) -> list[Chunk]:
    """Split parsed pages into overlapping chunks tagged with access-control metadata.

    Pages are concatenated into one token stream so a chunk is never cut short by a page break;
    a token-offset table maps each chunk back to the page it starts on.

    Args:
        pages: Cleaned pages in document order.
        document_id: Stable id used in citations and the eval datasets.
        department: Owning department; becomes a Qdrant payload field.
        access_level: Required access level; becomes a Qdrant payload field.
        chunk_size: settings.chunk_size_tokens.
        overlap: settings.chunk_overlap_tokens.

    Returns:
        Chunks in document order. An empty page list yields an empty list.

    Raises:
        ValueError: If overlap >= chunk_size, chunk_size < 1, or department/access_level is
            empty. An untagged chunk must be unconstructable.
    """
    if chunk_size < 1:
        raise ValueError(f"chunk_size must be >= 1, got {chunk_size}")
    if overlap < 0:
        raise ValueError(f"overlap must be >= 0, got {overlap}")
    if overlap >= chunk_size:
        raise ValueError(f"overlap must be smaller than chunk_size (got {overlap} >= {chunk_size})")
    if not department or not department.strip():
        raise ValueError(f"document {document_id} has no department; refusing to chunk it")
    if not access_level or not access_level.strip():
        raise ValueError(f"document {document_id} has no access_level; refusing to chunk it")

    if not pages:
        return []

    encoding = _encoding()
    tokens: list[int] = []
    # (token offset at which this page starts, page number)
    page_starts: list[tuple[int, int]] = []

    for index, page in enumerate(pages):
        page_tokens = encoding.encode(page.text)
        if not page_tokens:
            continue
        page_starts.append((len(tokens), page.page))
        tokens.extend(page_tokens)
        if index < len(pages) - 1:
            separator = encoding.encode("\n\n")
            tokens.extend(separator)

    if not tokens:
        return []

    stride = chunk_size - overlap
    chunks: list[Chunk] = []
    chunk_index = 0

    for start in range(0, len(tokens), stride):
        window = tokens[start : start + chunk_size]
        if not window:
            break
        text = encoding.decode(window).strip()
        if text:
            chunks.append(
                Chunk(
                    chunk_id=make_chunk_id(document_id, chunk_index, text),
                    document_id=document_id,
                    chunk_index=chunk_index,
                    text=text,
                    page=_page_for_offset(page_starts, start),
                    department=department.strip(),
                    access_level=access_level.strip(),
                )
            )
            chunk_index += 1
        if start + chunk_size >= len(tokens):
            break

    return chunks


def _page_for_offset(page_starts: list[tuple[int, int]], offset: int) -> int:
    """Return the page a token offset falls on -- the page where the chunk starts."""
    page = page_starts[0][1] if page_starts else 1
    for start_offset, page_number in page_starts:
        if start_offset <= offset:
            page = page_number
        else:
            break
    return page
