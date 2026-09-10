"""Translation of an authenticated Identity into a Qdrant pre-filter.

This is the single choke point for authorization (ADR-001). One function builds the filter, and
retrieval is not callable without one. If you ever find yourself filtering a result list by an
`allowed` flag, you are in the wrong module and reintroducing the exact bug this project exists
to avoid.

The access model (ADR-006) is ordinal levels plus a hard department partition:

* ``access_level`` is ranked ``public < internal < confidential``. A caller at level *n* reads
  every document at level <= *n*.
* ``department`` gates visibility absolutely. Engineering cannot read Finance documents at any
  level. The single exception is the reserved department ``all``, for genuinely org-wide
  documents, which every department may read subject to the level check.

The filter is returned as a plain dict: it is the canonical form for the access-decision log and
for assertions in tests, and vector_store converts it into a Qdrant Filter at the search call.
"""

from __future__ import annotations

from typing import Any

from app.auth import Identity

#: Ordinal ranking of access levels. The only place this ordering exists.
ACCESS_LEVEL_ORDER: dict[str, int] = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
}

#: Reserved department for org-wide documents readable by every department (ADR-006).
ORG_WIDE_DEPARTMENT = "all"


class AccessFilterError(Exception):
    """Raised when an access filter cannot be built for a caller."""


def visible_access_levels(access_level: str) -> list[str]:
    """Expand a caller access level into the set of levels they may read.

    Args:
        access_level: The caller's level, one of ACCESS_LEVEL_ORDER.

    Returns:
        Every level at or below the caller's, ordered from lowest to highest.

    Raises:
        AccessFilterError: If the level is unknown. An unrecognised level is never treated as
            permissive -- it is a configuration error and must stop the request.
    """
    normalised = (access_level or "").strip().lower()
    if normalised not in ACCESS_LEVEL_ORDER:
        raise AccessFilterError(
            f"unknown access_level {access_level!r}; expected one of "
            f"{sorted(ACCESS_LEVEL_ORDER, key=ACCESS_LEVEL_ORDER.get)}"  # type: ignore[arg-type]
        )
    ceiling = ACCESS_LEVEL_ORDER[normalised]
    return [
        level
        for level, rank in sorted(ACCESS_LEVEL_ORDER.items(), key=lambda kv: kv[1])
        if rank <= ceiling
    ]


def visible_departments(department: str) -> list[str]:
    """Return the departments a caller may read: their own, plus the org-wide bucket.

    Raises:
        AccessFilterError: If the caller has no department.
    """
    normalised = (department or "").strip().lower()
    if not normalised:
        raise AccessFilterError("identity has no department; refusing to build a filter")
    if normalised == ORG_WIDE_DEPARTMENT:
        raise AccessFilterError(
            f"{ORG_WIDE_DEPARTMENT!r} is a document-side department only; "
            "a user in it would bypass the partition"
        )
    return [normalised, ORG_WIDE_DEPARTMENT]


def build_access_filter(identity: Identity) -> dict[str, Any]:
    """Build the Qdrant filter restricting search to what this caller may see.

    Args:
        identity: The authenticated caller. There is no unauthenticated variant on purpose.

    Returns:
        A Qdrant filter in dict form, serialisable for the access-decision log.

    Raises:
        AccessFilterError: If the identity lacks a department or a recognised access level --
            an identity that cannot be constrained must never be allowed to search.
    """
    if identity is None:  # pragma: no cover - guards a caller-side mistake
        raise AccessFilterError("no identity supplied; retrieval requires an authenticated caller")

    departments = visible_departments(identity.department)
    levels = visible_access_levels(identity.access_level)

    return {
        "must": [
            {"key": "department", "match": {"any": departments}},
            {"key": "access_level", "match": {"any": levels}},
        ]
    }


def assert_filter_non_empty(qdrant_filter: dict[str, Any] | None) -> None:
    """Fail loudly if a filter would let everything through.

    Called immediately before every search. An empty filter is not a permissive default here;
    it is a bug.

    Raises:
        AccessFilterError: If the filter is None, empty, or has no `must` conditions.
    """
    if not qdrant_filter:
        raise AccessFilterError("refusing to search with an empty access filter")
    conditions = qdrant_filter.get("must")
    if not conditions:
        raise AccessFilterError("access filter has no `must` conditions; that is not a filter")
    keys = {condition.get("key") for condition in conditions if isinstance(condition, dict)}
    for required in ("department", "access_level"):
        if required not in keys:
            raise AccessFilterError(f"access filter is missing a condition on {required!r}")


def can_read(identity: Identity, department: str, access_level: str) -> bool:
    """Whether a caller may read a document with these tags.

    The relational document list uses this so the /documents view and the vector filter cannot
    diverge -- both derive from ACCESS_LEVEL_ORDER and the same partition rule.
    """
    try:
        return (department or "").strip().lower() in visible_departments(identity.department) and (
            access_level or ""
        ).strip().lower() in visible_access_levels(identity.access_level)
    except AccessFilterError:
        return False
