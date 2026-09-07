"""Tests for the permission pre-filter.

This is the project security claim in test form. A failure here is not a bug report, it is a
disclosure: unauthorized content reached, or could reach, the LLM context window.
"""


def test_filter_built_per_identity() -> None:
    """Each demo identity produces the exact expected Qdrant filter."""
    raise NotImplementedError


def test_search_is_never_called_without_a_filter() -> None:
    """Any code path reaching the vector store passes a non-empty filter.

    The regression guard for the whole class of bug: monkeypatch the client and fail if search
    is invoked with filter=None or an empty filter.
    """
    raise NotImplementedError


def test_restricted_document_never_returned() -> None:
    """For every demo user, no chunk from a document above their access level is returned."""
    raise NotImplementedError


def test_cross_department_isolation() -> None:
    """An Engineering user cannot retrieve Finance or HR chunks."""
    raise NotImplementedError


def test_identity_without_access_level_is_rejected() -> None:
    """An identity that cannot be constrained raises rather than searching unfiltered."""
    raise NotImplementedError


def test_policy_collection_uses_the_same_filter() -> None:
    """Contract review retrieval is filtered identically to chat retrieval."""
    raise NotImplementedError


def test_top_k_returns_k_authorized_chunks() -> None:
    """Pre-filtering means top_k is k authorized chunks, not k minus the restricted ones."""
    raise NotImplementedError


# TODO:
#  1. Blocked on ADR-006 open questions 1 and 2 (ordinal vs. tag levels; department partition).
#  2. Write test_search_is_never_called_without_a_filter first -- it is the highest-value test in
#     the repository and should exist before the filter itself is finished.
#  3. Drive test_restricted_document_never_returned from the demo users file, so adding a user
#     automatically extends coverage.
#  4. Assert on the captured context passed to the LLM, not only on the returned answer text.
