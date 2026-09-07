"""Tests for contract clause segmentation.

Verdict accuracy over badly segmented input is meaningless, so segmentation is tested and
reported separately (docs/EVALUATION.md section 6).
"""


def test_numbered_clauses_yield_gold_count() -> None:
    """A conventionally numbered contract segments into exactly the labeled clause count."""
    raise NotImplementedError


def test_unstructured_contract_routes_to_fallback() -> None:
    """A contract without usable numbering is segmented via the LLM path and labeled as such."""
    raise NotImplementedError


def test_headings_preserved_verbatim() -> None:
    """Clause headings survive segmentation unchanged, so gold alignment works."""
    raise NotImplementedError


def test_clause_spanning_pages_keeps_start_page() -> None:
    """A clause crossing a page boundary reports the page where it starts."""
    raise NotImplementedError


def test_empty_contract_returns_no_clauses() -> None:
    """An empty or unparseable contract returns zero clauses rather than raising."""
    raise NotImplementedError


# TODO:
#  1. Blocked on ADR-009 (what triggers the fallback).
#  2. Build fixtures from the frozen contract eval set so tests and evaluation agree on gold.
#  3. Include one contract using ARTICLE-style headings and one using 1.1 decimal numbering.
