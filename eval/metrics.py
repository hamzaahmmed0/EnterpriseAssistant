"""Metric implementations for the evaluation protocol.

Definitions live in docs/EVALUATION.md section 2 and are authoritative; this module implements
them and must not quietly diverge. A chunk is relevant when its (document_id, page) appears in the
item expected_sources.
"""

from dataclasses import dataclass


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


def precision_at_k(retrieved: list[RetrievedRef], gold: list[GoldSource], k: int = 5) -> float:
    """Fraction of the top k retrieved chunks that are relevant."""
    raise NotImplementedError


def recall_at_k(retrieved: list[RetrievedRef], gold: list[GoldSource], k: int = 5) -> float:
    """Fraction of distinct gold sources appearing in the top k."""
    raise NotImplementedError


def reciprocal_rank(retrieved: list[RetrievedRef], gold: list[GoldSource], k: int = 5) -> float:
    """Reciprocal rank of the first relevant chunk, or 0.0 if none in the top k."""
    raise NotImplementedError


def fallback_correctness(predicted_sufficient: list[bool]) -> float:
    """Fraction of negative-type items where the system correctly declined to answer."""
    raise NotImplementedError


def citation_validity(cited: list[GoldSource], context: list[RetrievedRef],
                      gold: list[GoldSource]) -> bool:
    """Whether every citation was in the supplied context and matches a gold source."""
    raise NotImplementedError


def macro_f1(confusion: dict[str, dict[str, int]]) -> float:
    """Macro-averaged F1 over the four contract verdict labels."""
    raise NotImplementedError


def latency_percentiles(samples: list[float]) -> dict[str, float]:
    """Return p50 and p95 for a list of per-query latencies."""
    raise NotImplementedError


# TODO:
#  1. Implement the three retrieval metrics; exclude items with expected_answerable=false from
#     precision/recall/MRR and route them to fallback_correctness instead.
#  2. Decide and document how a gold source with no matching page (DOCX) is compared.
#  3. Unit test each metric against a hand-computed example -- a wrong metric silently rewrites
#     every conclusion in the report.
#  4. Implement macro_f1 over the four verdict labels, handling a label with zero support.
#  5. Keep k a parameter, defaulting to 5, so a sweep can report other k without edits.
