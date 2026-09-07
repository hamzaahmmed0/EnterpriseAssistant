"""Translation of an authenticated Identity into a Qdrant pre-filter.

This is the single choke point for authorization (ADR-001). One function builds the filter, and
retrieval is not callable without one. If you ever find yourself filtering a result list by an
`allowed` flag, you are in the wrong module and reintroducing the exact bug this project exists
to avoid.
"""

from typing import Any

from app.auth import Identity


def build_access_filter(identity: Identity) -> dict[str, Any]:
    """Build the Qdrant filter restricting search to what this caller may see.

    Args:
        identity: The authenticated caller. There is no unauthenticated variant on purpose.

    Returns:
        A Qdrant filter, serialisable for the access-decision log.

    Raises:
        AccessFilterError: If the identity lacks a department or access level -- an identity that
            cannot be constrained must never be allowed to search.
    """
    raise NotImplementedError


def visible_access_levels(access_level: str) -> list[str]:
    """Expand a caller access level into the set of levels they may read.

    Whether this is an ordinal scale or an unordered tag set is ADR-006 open question 1.
    """
    raise NotImplementedError


def assert_filter_non_empty(qdrant_filter: dict[str, Any]) -> None:
    """Fail loudly if a filter would let everything through.

    Called immediately before every search. An empty filter is not a permissive default here;
    it is a bug.
    """
    raise NotImplementedError


class AccessFilterError(Exception):
    """Raised when an access filter cannot be built for a caller."""


# TODO:
#  1. Resolve ADR-006 open questions 1 and 2 (ordinal vs. tag access levels; is department a hard
#     partition?) before writing visible_access_levels() -- both change the filter shape.
#  2. Implement build_access_filter() returning a qdrant_client.models.Filter with must-conditions
#     on department and access_level.
#  3. Implement assert_filter_non_empty() and call it from vector_store.search().
#  4. Unit test: one case per demo user asserting the exact filter produced.
#  5. Unit test: a restricted document id never appears in results for a user without access, for
#     every demo user / restricted document pair.
#  6. Unit test (regression guard): monkeypatch the Qdrant client and fail if search() is ever
#     invoked with filter=None. This is the test that stops the whole class of bug.
#  7. Make the filter identical for documents_collection and policy_collection -- contract review
#     must not become a second, weaker path (ADR-007).
