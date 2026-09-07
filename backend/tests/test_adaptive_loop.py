"""Tests for the bounded adaptive retrieval loop.

Termination and the honest fallback are the two properties that must hold before any number from
Config C is trustworthy.
"""


def test_loop_terminates_at_cap() -> None:
    """A query that always scores below threshold stops after exactly max_attempts."""
    raise NotImplementedError


def test_sufficient_first_attempt_skips_reformulation() -> None:
    """A query clearing the threshold on attempt 1 never invokes the reformulation node."""
    raise NotImplementedError


def test_insufficient_evidence_is_a_normal_response() -> None:
    """The fallback returns an Answer with sufficient=False and no citations, not an exception."""
    raise NotImplementedError


def test_no_llm_call_when_evidence_insufficient() -> None:
    """When retrieval fails, no generation call is made, so no parametric answer can leak in."""
    raise NotImplementedError


def test_retry_still_applies_the_access_filter() -> None:
    """Every retry searches with the caller filter; widening k does not widen visibility."""
    raise NotImplementedError


def test_attempt_count_is_recorded() -> None:
    """RetrievalResult.attempts matches the number of retrieval calls actually made."""
    raise NotImplementedError


# TODO:
#  1. Blocked on ADR-004 (scoring function, cap, reformulation strategy).
#  2. Stub the scorer to force below-threshold results; do not depend on a live model for
#     termination tests.
#  3. test_retry_still_applies_the_access_filter is a security test, not a loop test -- keep it
#     even if the loop is rewritten.
