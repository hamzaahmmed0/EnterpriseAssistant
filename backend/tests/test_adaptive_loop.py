"""Tests for the bounded adaptive retrieval loop.

Termination and the honest fallback are the two properties that must hold before any number from
Config C is trustworthy. The judge and the vector store are both faked: a termination test that
depends on a live model is not a termination test.
"""

from __future__ import annotations

import pytest

from app.retrieval import adaptive as adaptive_module
from app.retrieval import engine as engine_module
from app.retrieval.scoring import EvidenceJudgement


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch, make_chunk):  # noqa: ANN201 - harness fixture
    """Install fakes for embedding, search, judging, and rewriting; return the call counters."""

    def _wire(*, scores: list[float], chunks_per_attempt: int = 2):
        calls = {"search": 0, "judge": 0, "reformulate": 0, "filters": []}
        remaining = list(scores)

        def fake_search(
            *, collection, query_vector, qdrant_filter, top_k, identity, score_floor=None
        ):  # noqa: ANN001, ANN202
            calls["search"] += 1
            calls["filters"].append(qdrant_filter)
            return [make_chunk(chunk_id=f"c{index}") for index in range(chunks_per_attempt)]

        def fake_judge(question, chunk_list):  # noqa: ANN001, ANN202
            calls["judge"] += 1
            score = remaining.pop(0) if remaining else 0.0
            return EvidenceJudgement(
                score=score, sufficient=score >= 0.6, missing="the specific accrual rate"
            )

        def fake_reformulate(state):  # noqa: ANN001, ANN202
            calls["reformulate"] += 1
            return {**state, "current_query": state["current_query"] + " accrual rate"}

        monkeypatch.setattr(engine_module, "search", fake_search)
        monkeypatch.setattr(engine_module, "embed_query", lambda text: [0.0] * 8)
        monkeypatch.setattr(adaptive_module, "judge_evidence", fake_judge)
        monkeypatch.setattr(adaptive_module, "node_reformulate", fake_reformulate)
        # Force the hand-rolled executor so the test does not depend on langgraph being installed.
        monkeypatch.setattr(
            adaptive_module, "build_adaptive_graph", lambda: (_ for _ in ()).throw(ImportError())
        )
        return calls

    return _wire


def _run(query: str, identity):  # noqa: ANN001, ANN202
    """Run the loop against the documents collection."""
    return adaptive_module.run_adaptive_retrieval(query, identity, "documents_collection")


# --------------------------------------------------------------------------- termination


def test_loop_terminates_at_cap(wire, hr_identity) -> None:
    """A query that always scores below threshold stops after exactly max_attempts."""
    calls = wire(scores=[0.1, 0.2, 0.3, 0.4, 0.5])  # more scores than attempts allowed

    result = _run("what is the leave accrual rate?", hr_identity)

    assert result.attempts == 3, "loop did not stop at ADAPTIVE_MAX_ATTEMPTS"
    assert calls["search"] == 3
    assert calls["judge"] == 3
    assert result.sufficient is False


def test_cap_is_respected_even_when_scores_keep_rising(wire, hr_identity) -> None:
    """Improving-but-still-insufficient evidence does not buy extra attempts."""
    wire(scores=[0.1, 0.3, 0.55, 0.99])
    result = _run("what is the leave accrual rate?", hr_identity)
    assert result.attempts == 3
    assert result.sufficient is False


def test_sufficient_first_attempt_skips_reformulation(wire, hr_identity) -> None:
    """A query clearing the threshold on attempt 1 never invokes the reformulation node."""
    calls = wire(scores=[0.9])

    result = _run("how much annual leave do I accrue?", hr_identity)

    assert result.attempts == 1
    assert calls["reformulate"] == 0
    assert calls["search"] == 1
    assert result.sufficient is True


def test_retry_then_success_reports_two_attempts(wire, hr_identity) -> None:
    """The attempt count is the real number of retrievals, not a constant."""
    calls = wire(scores=[0.2, 0.85])

    result = _run("leave accrual", hr_identity)

    assert result.attempts == 2
    assert calls["reformulate"] == 1
    assert result.sufficient is True


def test_attempt_count_matches_search_calls(wire, hr_identity) -> None:
    """RetrievalResult.attempts must match the number of retrieval calls actually made."""
    calls = wire(scores=[0.1, 0.1, 0.1])
    result = _run("something obscure", hr_identity)
    assert result.attempts == calls["search"]


# --------------------------------------------------------------------------- honest fallback


def test_insufficient_evidence_is_a_normal_response(wire, hr_identity) -> None:
    """The fallback is a returned result with sufficient=False, not an exception."""
    wire(scores=[0.0, 0.0, 0.0])
    result = _run("what is the CEO home address?", hr_identity)
    assert result.sufficient is False
    assert result.attempts == 3


def test_no_llm_call_when_evidence_insufficient(wire, hr_identity, monkeypatch) -> None:
    """When retrieval fails, generation is never invoked, so no parametric answer can leak in."""
    from app.generation import answer as answer_module

    wire(scores=[0.0, 0.0, 0.0])
    called = {"complete": 0}

    def fake_complete(*args: object, **kwargs: object):  # noqa: ANN202
        called["complete"] += 1
        raise AssertionError("generation was called despite insufficient evidence")

    monkeypatch.setattr(answer_module, "complete", fake_complete)

    result = _run("unanswerable", hr_identity)
    generated = answer_module.generate_answer("unanswerable", result)

    assert called["complete"] == 0
    assert generated.sufficient is False
    assert generated.citations == []


# --------------------------------------------------------------------------- security


def test_retry_still_applies_the_access_filter(wire, hr_identity) -> None:
    """Every retry searches with the caller's filter; widening the query never widens visibility.

    This is a security test, not a loop test. Keep it even if the loop is rewritten.
    """
    calls = wire(scores=[0.1, 0.1, 0.1])

    _run("leave policy", hr_identity)

    assert len(calls["filters"]) == 3
    for applied in calls["filters"]:
        assert applied, "a retry reached the store with no filter"
        conditions = {
            condition["key"]: set(condition["match"]["any"]) for condition in applied["must"]
        }
        assert conditions["department"] == {"hr", "all"}
        assert conditions["access_level"] == {"public", "internal"}


def test_every_attempt_uses_the_same_identity(wire, engineering_identity) -> None:
    """A reformulated query is still asked as the original caller."""
    calls = wire(scores=[0.1, 0.1, 0.1])
    _run("payroll", engineering_identity)
    for applied in calls["filters"]:
        conditions = {
            condition["key"]: set(condition["match"]["any"]) for condition in applied["must"]
        }
        assert conditions["department"] == {"engineering", "all"}


# --------------------------------------------------------------------------- empty evidence


def test_no_chunks_scores_zero_without_calling_the_judge(hr_identity) -> None:
    """An empty retrieval is defined as score 0 and costs no LLM call."""
    from app.retrieval.scoring import judge_evidence

    judgement = judge_evidence("anything", [])
    assert judgement.score == 0.0
    assert judgement.sufficient is False
