"""Tests for fixed-size chunking with overlap.

Chunking breaks silently: bad boundaries degrade retrieval without raising anything. These tests
exist so that failure is loud.
"""

from __future__ import annotations

import pytest

from app.ingestion.chunking import Chunk, chunk_pages, count_tokens, make_chunk_id

pytest.importorskip("tiktoken", reason="chunk size is measured in tiktoken tokens (ADR-003)")

TAGS = {"document_id": "hr-leave-policy", "department": "hr", "access_level": "internal"}


def _tokens(count: int, word: str = "policy") -> str:
    """Build text of roughly `count` tokens. Each word here is a single cl100k token."""
    return " ".join([word] * count)


def _chunk(pages, size: int = 50, overlap: int = 10) -> list[Chunk]:
    """Chunk with explicit parameters so tests never depend on the ambient config."""
    return chunk_pages(
        pages, TAGS["document_id"], TAGS["department"], TAGS["access_level"], size, overlap
    )


# --------------------------------------------------------------------------- sizing


def test_short_document_produces_single_chunk(make_pages) -> None:
    """A document shorter than chunk_size yields one chunk with the correct page."""
    chunks = _chunk(make_pages("Employees accrue twenty days of paid annual leave."))
    assert len(chunks) == 1
    assert chunks[0].page == 1
    assert chunks[0].chunk_index == 0


def test_chunk_never_exceeds_configured_size(make_pages) -> None:
    """No chunk may exceed chunk_size tokens; oversized chunks silently truncate context."""
    chunks = _chunk(make_pages(_tokens(400)), size=50, overlap=10)
    assert len(chunks) > 1
    for chunk in chunks:
        assert count_tokens(chunk.text) <= 50


def test_boundary_at_exactly_chunk_size(make_pages) -> None:
    """A document of exactly chunk_size tokens produces exactly one chunk."""
    size = 40
    chunks = _chunk(make_pages(_tokens(size)), size=size, overlap=8)
    assert len(chunks) == 1


def test_one_token_over_chunk_size_produces_two(make_pages) -> None:
    """One token past the boundary rolls over rather than being dropped."""
    size = 40
    chunks = _chunk(make_pages(_tokens(size + 1)), size=size, overlap=8)
    assert len(chunks) == 2


# --------------------------------------------------------------------------- overlap


def test_overlap_is_actually_shared(make_pages) -> None:
    """Consecutive chunks share text; an overlap setting that does nothing is worse than none."""
    chunks = _chunk(make_pages(" ".join(f"word{i}" for i in range(300))), size=50, overlap=15)
    assert len(chunks) >= 2

    first_words = chunks[0].text.split()
    second_words = chunks[1].text.split()
    shared = set(first_words[-15:]) & set(second_words[:15])
    assert shared, "consecutive chunks share no tokens; overlap is not being applied"


def test_overlap_greater_than_size_is_rejected(make_pages) -> None:
    """Overlap >= chunk_size raises rather than looping forever."""
    with pytest.raises(ValueError, match="smaller than chunk_size"):
        _chunk(make_pages(_tokens(100)), size=20, overlap=20)
    with pytest.raises(ValueError):
        _chunk(make_pages(_tokens(100)), size=20, overlap=50)


def test_zero_overlap_is_allowed(make_pages) -> None:
    """Zero overlap is a legitimate sweep point, not an error."""
    assert _chunk(make_pages(_tokens(120)), size=40, overlap=0)


# --------------------------------------------------------------------------- provenance


def test_page_attribution_across_boundary(make_pages) -> None:
    """A chunk spanning two pages is attributed to the page where it starts (ADR-012)."""
    pages = make_pages(_tokens(30, "alpha"), _tokens(30, "beta"), _tokens(30, "gamma"))
    chunks = _chunk(pages, size=25, overlap=5)

    assert chunks[0].page == 1
    assert [chunk.page for chunk in chunks] == sorted(chunk.page for chunk in chunks)
    assert max(chunk.page for chunk in chunks) <= 3


def test_pages_are_preserved_not_reset(make_pages) -> None:
    """Content from later pages keeps its own page number."""
    pages = make_pages(_tokens(60, "alpha"), _tokens(60, "omega"))
    chunks = _chunk(pages, size=30, overlap=5)
    pages_seen = {chunk.page for chunk in chunks}
    assert pages_seen == {1, 2}


def test_empty_page_list_yields_no_chunks() -> None:
    """An empty document is a reportable result, not a crash."""
    assert _chunk([]) == []


def test_blank_pages_are_skipped(make_pages) -> None:
    """A page that extracts to nothing must not become an empty chunk."""
    chunks = _chunk(make_pages("", "   ", _tokens(20)))
    assert len(chunks) == 1
    assert chunks[0].text.strip()


# --------------------------------------------------------------------------- tagging


def test_untagged_chunk_is_rejected(make_pages) -> None:
    """Chunking without a department or access level raises rather than producing a chunk."""
    pages = make_pages(_tokens(20))
    with pytest.raises(ValueError, match="department"):
        chunk_pages(pages, "doc", "", "internal", 50, 10)
    with pytest.raises(ValueError, match="access_level"):
        chunk_pages(pages, "doc", "hr", "", 50, 10)


def test_every_chunk_carries_its_tags(make_pages) -> None:
    """Tags are copied onto every chunk, because that is what the Qdrant payload asserts on."""
    chunks = _chunk(make_pages(_tokens(200)), size=40, overlap=8)
    for chunk in chunks:
        assert chunk.department == "hr"
        assert chunk.access_level == "internal"
        assert chunk.document_id == "hr-leave-policy"


# --------------------------------------------------------------------------- idempotence


def test_chunk_ids_are_deterministic(make_pages) -> None:
    """The same input produces the same chunk ids, so re-ingest is idempotent (ADR-008)."""
    pages = make_pages(_tokens(200))
    first = [chunk.chunk_id for chunk in _chunk(pages, size=40, overlap=8)]
    second = [chunk.chunk_id for chunk in _chunk(pages, size=40, overlap=8)]
    assert first == second
    assert len(set(first)) == len(first), "chunk ids collided within one document"


def test_chunk_id_changes_when_text_changes() -> None:
    """Reject id reuse when the text changes.

    Otherwise a re-ingest would silently keep the stale vector for an edited document.
    """
    assert make_chunk_id("doc", 0, "original text") != make_chunk_id("doc", 0, "edited text")


def test_indexes_are_sequential(make_pages) -> None:
    """chunk_index is dense and ordered; the eval joins on it."""
    chunks = _chunk(make_pages(_tokens(300)), size=40, overlap=8)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
