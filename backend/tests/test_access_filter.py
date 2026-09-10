"""Tests for the permission pre-filter.

This is the project's security claim in test form. A failure here is not a bug report, it is a
disclosure: unauthorized content reached, or could reach, the LLM context window.
"""

from __future__ import annotations

import pytest

from app.auth import Identity
from app.retrieval.access_filter import (
    ORG_WIDE_DEPARTMENT,
    AccessFilterError,
    assert_filter_non_empty,
    build_access_filter,
    can_read,
    visible_access_levels,
    visible_departments,
)


def _conditions(built: dict) -> dict[str, set[str]]:
    """Flatten a built filter into {field: allowed values} for readable assertions."""
    return {condition["key"]: set(condition["match"]["any"]) for condition in built["must"]}


# --------------------------------------------------------------------------- level ordering


def test_ordinal_levels_subsume_lower_ones() -> None:
    """A caller at `confidential` reads every level; `public` reads only its own."""
    assert visible_access_levels("confidential") == ["public", "internal", "confidential"]
    assert visible_access_levels("internal") == ["public", "internal"]
    assert visible_access_levels("public") == ["public"]


def test_unknown_level_is_rejected_not_widened() -> None:
    """An unrecognised level is a configuration error, never a permissive default."""
    with pytest.raises(AccessFilterError):
        visible_access_levels("top-secret")
    with pytest.raises(AccessFilterError):
        visible_access_levels("")


# --------------------------------------------------------------------------- department partition


def test_department_partition_includes_only_own_and_org_wide() -> None:
    """Department is a hard partition; the org-wide bucket is the single exception (ADR-006)."""
    assert set(visible_departments("engineering")) == {"engineering", ORG_WIDE_DEPARTMENT}


def test_user_cannot_sit_in_the_org_wide_department() -> None:
    """A user in `all` would bypass the partition entirely, so it is rejected."""
    with pytest.raises(AccessFilterError):
        visible_departments(ORG_WIDE_DEPARTMENT)


def test_identity_without_department_is_rejected() -> None:
    """An identity that cannot be constrained raises rather than searching unfiltered."""
    identity = Identity(user_id="x", name="X", department="", access_level="internal", role="r")
    with pytest.raises(AccessFilterError):
        build_access_filter(identity)


def test_identity_without_access_level_is_rejected() -> None:
    """Same, for a missing access level."""
    identity = Identity(user_id="x", name="X", department="hr", access_level="", role="r")
    with pytest.raises(AccessFilterError):
        build_access_filter(identity)


# --------------------------------------------------------------------------- built filter


def test_filter_built_per_identity(all_identities: list[Identity]) -> None:
    """Each demo identity produces the exact expected filter."""
    expected = {
        "hr_generalist": ({"hr", "all"}, {"public", "internal"}),
        "hr_director": ({"hr", "all"}, {"public", "internal", "confidential"}),
        "eng_ic": ({"engineering", "all"}, {"public", "internal"}),
        "fin_controller": ({"finance", "all"}, {"public", "internal", "confidential"}),
    }
    for identity in all_identities:
        departments, levels = expected[identity.user_id]
        built = _conditions(build_access_filter(identity))
        assert built["department"] == departments, identity.user_id
        assert built["access_level"] == levels, identity.user_id


def test_filter_always_constrains_both_fields(all_identities: list[Identity]) -> None:
    """Neither dimension may be dropped: one without the other is a hole, not a filter."""
    for identity in all_identities:
        assert_filter_non_empty(build_access_filter(identity))


@pytest.mark.parametrize(
    "bad_filter",
    [
        None,
        {},
        {"must": []},
        {"must": [{"key": "department", "match": {"any": ["hr"]}}]},  # level missing
        {"must": [{"key": "access_level", "match": {"any": ["public"]}}]},  # department missing
    ],
)
def test_incomplete_filters_are_refused(bad_filter: dict | None) -> None:
    """assert_filter_non_empty is the last gate before search; it must reject every partial."""
    with pytest.raises(AccessFilterError):
        assert_filter_non_empty(bad_filter)


# --------------------------------------------------------------------------- visibility matrix


def test_restricted_document_never_visible(
    all_identities: list[Identity], corpus: list[dict]
) -> None:
    """For every demo user, no document above their level or outside their department is visible.

    Driven from the identity and corpus fixtures, so adding a user or a document automatically
    extends coverage.
    """
    expected_visible = {
        "hr_generalist": {"hr-handbook", "hr-leave-policy"},
        "hr_director": {"hr-handbook", "hr-leave-policy", "hr-comp-review"},
        "eng_ic": {"hr-handbook", "eng-oncall"},
        "fin_controller": {"hr-handbook", "fin-procurement", "fin-salary-bands"},
    }

    for identity in all_identities:
        visible = {
            document["document_id"]
            for document in corpus
            if can_read(identity, document["department"], document["access_level"])
        }
        assert visible == expected_visible[identity.user_id], identity.user_id


def test_cross_department_isolation(engineering_identity: Identity, corpus: list[dict]) -> None:
    """An Engineering user cannot retrieve Finance or HR department chunks at any level."""
    for document in corpus:
        if document["department"] in {"finance", "hr"}:
            assert not can_read(
                engineering_identity, document["department"], document["access_level"]
            ), document["document_id"]


def test_level_boundary_within_one_department(
    hr_identity: Identity, hr_director_identity: Identity
) -> None:
    """Same department, different level: the demo that shows access control is real."""
    assert not can_read(hr_identity, "hr", "confidential")
    assert can_read(hr_director_identity, "hr", "confidential")


def test_org_wide_documents_readable_across_departments(all_identities: list[Identity]) -> None:
    """The `all` bucket is a deliberate widening, so it is tested explicitly rather than assumed."""
    for identity in all_identities:
        assert can_read(identity, ORG_WIDE_DEPARTMENT, "public")


def test_filter_is_not_collection_specific(hr_identity: Identity) -> None:
    """The policy collection gets the same filter as the document collection (ADR-007).

    build_access_filter takes no collection argument, so contract review cannot become a second,
    weaker path. This test fails if someone adds one.
    """
    import inspect

    signature = inspect.signature(build_access_filter)
    assert list(signature.parameters) == ["identity"]
