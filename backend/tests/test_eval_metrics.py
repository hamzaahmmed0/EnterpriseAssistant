"""Tests for the evaluation metrics.

A wrong metric silently rewrites every conclusion in the final report, so each one is checked
against a hand-computed example rather than against itself.

The eval package lives at the repository root rather than under backend/, so it is added to the
path here instead of being importable by default.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.metrics import (  # noqa: E402
    GoldSource,
    RetrievedRef,
    accuracy,
    citation_validity,
    confusion_matrix,
    fallback_correctness,
    latency_percentiles,
    macro_f1,
    mean,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)

GOLD = [GoldSource("hr-leave-policy", 2)]
GOLD_TWO = [GoldSource("hr-leave-policy", 2), GoldSource("hr-handbook", 5)]


def _refs(*pairs: tuple[str, int]) -> list[RetrievedRef]:
    """Build a ranked retrieval list from (document_id, page) pairs."""
    return [
        RetrievedRef(document_id=doc, page=page, rank=rank)
        for rank, (doc, page) in enumerate(pairs, start=1)
    ]


# --------------------------------------------------------------------------- precision


def test_precision_denominator_is_k_not_the_result_count() -> None:
    """Returning fewer results must not inflate precision.

    One hit out of two returned is 1/5 at k=5, not 1/2 -- otherwise a config that retrieves less
    scores better for retrieving less.
    """
    retrieved = _refs(("hr-leave-policy", 2), ("eng-oncall", 1))
    assert precision_at_k(retrieved, GOLD, k=5) == pytest.approx(0.2)


def test_precision_counts_every_relevant_hit() -> None:
    """Two relevant chunks in the top 5 is 0.4."""
    retrieved = _refs(("hr-leave-policy", 2), ("hr-handbook", 5), ("eng-oncall", 1))
    assert precision_at_k(retrieved, GOLD_TWO, k=5) == pytest.approx(0.4)


def test_precision_is_zero_with_no_hits() -> None:
    """No relevant chunk means zero, not an error."""
    assert precision_at_k(_refs(("eng-oncall", 1)), GOLD, k=5) == 0.0


def test_metrics_reject_items_with_no_gold() -> None:
    """Negatives have no gold sources and must be routed to fallback_correctness instead."""
    for metric in (precision_at_k, recall_at_k, reciprocal_rank):
        with pytest.raises(ValueError):
            metric(_refs(("a", 1)), [], 5)


# --------------------------------------------------------------------------- recall


def test_recall_over_multiple_gold_sources() -> None:
    """Finding one of two required sources is 0.5 -- the multi_hop case."""
    retrieved = _refs(("hr-leave-policy", 2), ("eng-oncall", 1))
    assert recall_at_k(retrieved, GOLD_TWO, k=5) == pytest.approx(0.5)


def test_recall_deduplicates_gold() -> None:
    """Retrieving the same gold page twice does not count twice."""
    retrieved = _refs(("hr-leave-policy", 2), ("hr-leave-policy", 2))
    assert recall_at_k(retrieved, GOLD, k=5) == pytest.approx(1.0)


def test_recall_respects_the_cutoff() -> None:
    """A gold chunk ranked below k does not count."""
    retrieved = _refs(("a", 1), ("b", 1), ("c", 1), ("d", 1), ("e", 1), ("hr-leave-policy", 2))
    assert recall_at_k(retrieved, GOLD, k=5) == 0.0
    assert recall_at_k(retrieved, GOLD, k=6) == pytest.approx(1.0)


# --------------------------------------------------------------------------- MRR


@pytest.mark.parametrize(("position", "expected"), [(1, 1.0), (2, 0.5), (3, 1 / 3), (4, 0.25)])
def test_reciprocal_rank_by_position(position: int, expected: float) -> None:
    """RR is 1/rank of the first relevant chunk."""
    pairs = [("filler", index) for index in range(1, position)] + [("hr-leave-policy", 2)]
    assert reciprocal_rank(_refs(*pairs), GOLD, k=5) == pytest.approx(expected)


def test_reciprocal_rank_is_zero_when_absent() -> None:
    """No relevant chunk in the top k is 0, not undefined."""
    assert reciprocal_rank(_refs(("eng-oncall", 1)), GOLD, k=5) == 0.0


# --------------------------------------------------------------------------- fallback


def test_fallback_correctness_counts_declines() -> None:
    """Correct behaviour on a negative item is declining to answer."""
    assert fallback_correctness([False, False, True, False]) == pytest.approx(0.75)


def test_fallback_correctness_of_nothing_is_zero() -> None:
    """No negative items means no credit, not a divide-by-zero."""
    assert fallback_correctness([]) == 0.0


# --------------------------------------------------------------------------- citations


def test_citation_valid_requires_context_and_gold() -> None:
    """A citation must be in the context supplied *and* be a gold source."""
    context = _refs(("hr-leave-policy", 2))
    assert citation_validity([GoldSource("hr-leave-policy", 2)], context, GOLD) is True


def test_citation_outside_the_context_is_invalid() -> None:
    """Citing a document that was never in the context is a groundedness failure."""
    context = _refs(("hr-leave-policy", 2))
    assert citation_validity([GoldSource("fin-salary-bands", 1)], context, GOLD) is False


def test_no_citation_is_invalid() -> None:
    """Citation is required, so an uncited answer scores as a failure."""
    assert citation_validity([], _refs(("hr-leave-policy", 2)), GOLD) is False


# --------------------------------------------------------------------------- classification


def test_confusion_matrix_counts_pairs() -> None:
    """Rows are gold, columns predicted."""
    labels = ["Compliant", "Deviates"]
    matrix = confusion_matrix(
        [("Compliant", "Compliant"), ("Compliant", "Deviates"), ("Deviates", "Deviates")], labels
    )
    assert matrix["Compliant"]["Compliant"] == 1
    assert matrix["Compliant"]["Deviates"] == 1
    assert matrix["Deviates"]["Deviates"] == 1
    assert matrix["Deviates"]["Compliant"] == 0


def test_accuracy_from_the_matrix() -> None:
    """Accuracy is the trace over the total."""
    labels = ["Compliant", "Deviates"]
    matrix = confusion_matrix(
        [("Compliant", "Compliant"), ("Compliant", "Deviates"), ("Deviates", "Deviates")], labels
    )
    assert accuracy(matrix) == pytest.approx(2 / 3)


def test_macro_f1_is_one_for_a_perfect_matrix() -> None:
    """A diagonal matrix scores 1.0."""
    labels = ["Compliant", "Deviates"]
    matrix = confusion_matrix([("Compliant", "Compliant"), ("Deviates", "Deviates")], labels)
    assert macro_f1(matrix) == pytest.approx(1.0)


def test_macro_f1_penalises_an_unsupported_label() -> None:
    """A label with zero support contributes 0.0 rather than being skipped.

    With four verdicts over a handful of contracts, Missing and Needs Legal Review will be rare;
    dropping them would flatter the score exactly where the corpus is weakest.
    """
    labels = ["Compliant", "Deviates", "Missing", "Needs Legal Review"]
    matrix = confusion_matrix([("Compliant", "Compliant"), ("Deviates", "Deviates")], labels)
    assert macro_f1(matrix) == pytest.approx(0.5)


# --------------------------------------------------------------------------- latency


def test_latency_percentiles() -> None:
    """p50 and p95 by nearest rank."""
    samples = [float(value) for value in range(1, 21)]
    percentiles = latency_percentiles(samples)
    assert percentiles["p50"] == pytest.approx(10.0)
    assert percentiles["p95"] == pytest.approx(19.0)


def test_latency_of_nothing_is_zero() -> None:
    """An empty sample set reports zeros rather than raising."""
    assert latency_percentiles([]) == {"p50": 0.0, "p95": 0.0}


def test_mean_of_empty_is_zero() -> None:
    """Used throughout the aggregation; must not divide by zero."""
    assert mean([]) == 0.0
