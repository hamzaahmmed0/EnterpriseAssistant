"""Tests for fixed-size chunking with overlap.

Chunking breaks silently: bad boundaries degrade retrieval without raising anything. These tests
exist so that failure is loud.
"""


def test_chunk_size_boundary() -> None:
    """A document of exactly chunk_size tokens produces exactly one chunk."""
    raise NotImplementedError


def test_overlap_is_actually_shared() -> None:
    """Consecutive chunks share the configured number of overlapping tokens."""
    raise NotImplementedError


def test_short_document_produces_single_chunk() -> None:
    """A document shorter than chunk_size yields one chunk with the correct page."""
    raise NotImplementedError


def test_page_attribution_across_boundary() -> None:
    """A chunk spanning two pages is attributed to the page where it starts."""
    raise NotImplementedError


def test_untagged_chunk_is_rejected() -> None:
    """Chunking without a department or access level raises rather than producing a chunk."""
    raise NotImplementedError


def test_chunk_ids_are_deterministic() -> None:
    """The same input produces the same chunk ids, so re-ingest is idempotent."""
    raise NotImplementedError


def test_overlap_greater_than_size_is_rejected() -> None:
    """Overlap >= chunk_size raises rather than looping."""
    raise NotImplementedError


# TODO:
#  1. Blocked on ADR-003 (chunk size, overlap, token vs. character) -- write these once decided.
#  2. Use a real extracted page from the synthetic corpus as one fixture, not only synthetic text.
#  3. Add a property test: total chunk text minus overlap reconstructs the source document.
