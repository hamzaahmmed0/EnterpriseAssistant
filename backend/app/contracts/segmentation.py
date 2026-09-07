"""Clause-level segmentation of uploaded contracts (ADR-009).

Structure-first (headings and numbering), with an LLM classification fallback for documents the
structural pass cannot segment. Segmentation quality is reported separately in
docs/EVALUATION.md, because verdict accuracy over badly segmented input means nothing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Clause:
    """One segmented contract clause."""

    clause_index: int
    heading: str
    text: str
    page: int
    segmentation_path: str


def segment_contract(text_by_page: list[tuple[int, str]]) -> list[Clause]:
    """Segment a parsed contract into clauses, choosing the structural or fallback path."""
    raise NotImplementedError


def segment_structural(text_by_page: list[tuple[int, str]]) -> list[Clause]:
    """Segment on numbered headings. Returns an empty list when no structure is found."""
    raise NotImplementedError


def segment_with_llm(text_by_page: list[tuple[int, str]]) -> list[Clause]:
    """Segment via LLM classification, for contracts without usable structure."""
    raise NotImplementedError


def should_use_fallback(structural_clauses: list[Clause]) -> bool:
    """Decide whether the structural result is good enough to keep."""
    raise NotImplementedError


# TODO:
#  1. Resolve the ADR-009 open question (what triggers the fallback: zero matches, a clause-count
#     threshold, or a clause-length heuristic) before implementing should_use_fallback().
#  2. Implement segment_structural() against the numbering conventions used in the eval contracts
#     (1., 1.1, ARTICLE N); list the patterns supported in the docstring.
#  3. Implement segment_with_llm() with a bounded single pass -- no retry loop here.
#  4. Set segmentation_path on every Clause so the eval can report which path each contract took.
#  5. Test: a contract with conventional numbering yields exactly the gold clause count.
#  6. Test: a contract with no numbering routes to the fallback and is labelled as such.
#  7. Test: heading text is preserved verbatim; the eval aligns predicted to gold clauses by it.
#  8. Test: a clause spanning a page boundary keeps the page where it starts.
