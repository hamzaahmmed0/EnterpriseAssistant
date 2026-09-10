"""Metric implementations for the evaluation protocol.

Definitions live in docs/EVALUATION.md section 2 and are authoritative; this module implements
them and must not quietly diverge. A retrieved chunk is **relevant** when its
``(document_id, page)`` appears in that item's ``expected_sources``.

Items with ``expected_answerable: false`` carry no gold sources. They are excluded from
precision/recall/MRR and scored by ``fallback_correctness`` instead -- averaging a zero into
precision for a question that has no right answer would understate every configuration equally
and hide the thing worth measuring.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_K = 5


@dataclass(frozen=True)
class GoldSource:
    """One expected source for a ground-truth question."""

    document_id: str
    page: int


@dataclass(frozen=True)
class RetrievedRef:
    """A retrieved chunk reduced to what the metrics need."""

    document_id: str
    page: int
    rank: int


def _top(retrieved: list[RetrievedRef], k: int) -> list[RetrievedRef]:
    """The k highest-ranked refs, ordered by rank."""
    return sorted(retrieved, key=lambda ref: ref.rank)[:k]


def _matches(ref: RetrievedRef, gold: list[GoldSource]) -> bool:
    """Whether a retrieved ref hits any gold source."""
    return any(ref.document_id == item.document_id and ref.page == item.page for item in gold)


def precision_at_k(
    retrieved: list[RetrievedRef], gold: list[GoldSource], k: int = DEFAULT_K
) -> float:
    """Fraction of the top k retrieved chunks that are relevant.

    The denominator is k, not len(retrieved): retrieving three chunks of which two are relevant
    is not the same as retrieving five of which two are, and the former should not score higher
    for having returned less.
    """
    if not gold:
        raise ValueError("precision_at_k is undefined for an item with no gold sources")
    hits = sum(1 for ref in _top(retrieved, k) if _matches(ref, gold))
    return hits / k


def recall_at_k(retrieved: list[RetrievedRef], gold: list[GoldSource], k: int = DEFAULT_K) -> float:
    """Fraction of distinct gold sources appearing in the top k.

    This is where multi_hop and cross_document items are decisive: a config that finds one of two
    required sources scores 0.5 here while precision may look healthy.
    """
    if not gold:
        raise ValueError("recall_at_k is undefined for an item with no gold sources")
    unique_gold = {(item.document_id, item.page) for item in gold}
    found = {
        (ref.document_id, ref.page)
        for ref in _top(retrieved, k)
        if (ref.document_id, ref.page) in unique_gold
    }
    return len(found) / len(unique_gold)


def reciprocal_rank(
    retrieved: list[RetrievedRef], gold: list[GoldSource], k: int = DEFAULT_K
) -> float:
    """Reciprocal rank of the first relevant chunk, or 0.0 if none is in the top k."""
    if not gold:
        raise ValueError("reciprocal_rank is undefined for an item with no gold sources")
    for position, ref in enumerate(_top(retrieved, k), start=1):
        if _matches(ref, gold):
            return 1.0 / position
    return 0.0


def fallback_correctness(predicted_sufficient: list[bool]) -> float:
    """Fraction of negative-type items where the system correctly declined to answer.

    Args:
        predicted_sufficient: One entry per `negative` item -- what the system claimed. Correct
            behaviour is False (it returned the insufficient-evidence answer).

    A confident wrong answer here is the worst failure mode in the project, so this is reported
    on its own line rather than folded into an accuracy average.
    """
    if not predicted_sufficient:
        return 0.0
    declined = sum(1 for sufficient in predicted_sufficient if not sufficient)
    return declined / len(predicted_sufficient)


def citation_validity(
    cited: list[GoldSource],
    context: list[RetrievedRef],
    gold: list[GoldSource],
) -> bool:
    """Whether every citation was in the supplied context *and* matches a gold source.

    Both halves matter: a citation outside the context is a groundedness failure, and a citation
    inside the context but not in gold is a correctness failure. An answer with no citations at
    all counts as invalid, because citation is required.
    """
    if not cited:
        return False
    in_context = {(ref.document_id, ref.page) for ref in context}
    in_gold = {(item.document_id, item.page) for item in gold}
    return all(
        (item.document_id, item.page) in in_context and (item.document_id, item.page) in in_gold
        for item in cited
    )


def confusion_matrix(pairs: list[tuple[str, str]], labels: list[str]) -> dict[str, dict[str, int]]:
    """Build a confusion matrix from (gold, predicted) label pairs.

    Rows are gold labels, columns predicted, matching the table layout in docs/EVALUATION.md.
    """
    matrix = {gold: {predicted: 0 for predicted in labels} for gold in labels}
    for gold, predicted in pairs:
        if gold in matrix and predicted in matrix[gold]:
            matrix[gold][predicted] += 1
    return matrix


def macro_f1(confusion: dict[str, dict[str, int]]) -> float:
    """Macro-averaged F1 over the labels present in the matrix.

    A label with zero support contributes 0.0 rather than being skipped: with four verdicts and
    a handful of contracts, `Missing` and `Needs Legal Review` will be rare, and quietly dropping
    an unsupported label would flatter the score.
    """
    labels = list(confusion)
    if not labels:
        return 0.0

    scores: list[float] = []
    for label in labels:
        true_positive = confusion[label][label]
        false_negative = sum(confusion[label][other] for other in labels if other != label)
        false_positive = sum(confusion[other][label] for other in labels if other != label)

        precision = (
            true_positive / (true_positive + false_positive)
            if (true_positive + false_positive)
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if (true_positive + false_negative)
            else 0.0
        )
        scores.append(
            2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        )

    return sum(scores) / len(scores)


def accuracy(confusion: dict[str, dict[str, int]]) -> float:
    """Overall accuracy from a confusion matrix."""
    total = sum(sum(row.values()) for row in confusion.values())
    if not total:
        return 0.0
    correct = sum(confusion[label][label] for label in confusion)
    return correct / total


def latency_percentiles(samples: list[float]) -> dict[str, float]:
    """Return p50 and p95 for a list of per-query latencies (nearest-rank method)."""
    if not samples:
        return {"p50": 0.0, "p95": 0.0}
    ordered = sorted(samples)

    def percentile(fraction: float) -> float:
        # Nearest rank: ceil(fraction * n). round() is wrong here -- it breaks .5 to even, so
        # p95 of 20 samples would land on rank 20 instead of 19.
        index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
        return ordered[index]

    return {"p50": percentile(0.50), "p95": percentile(0.95)}


def mean(values: list[float]) -> float:
    """Arithmetic mean, defined as 0.0 for an empty list."""
    return sum(values) / len(values) if values else 0.0
