"""Tests for contract clause segmentation.

Verdict accuracy over badly segmented input is meaningless, so segmentation is tested and
reported separately (docs/EVALUATION.md section 6).
"""

from __future__ import annotations

import pytest

from app.contracts import segmentation
from app.contracts.segmentation import (
    LLM_FALLBACK,
    STRUCTURAL,
    Clause,
    segment_contract,
    segment_structural,
    should_use_fallback,
)

DECIMAL_CONTRACT = """MASTER SERVICES AGREEMENT
This agreement is made between the parties named below.

1. Definitions
"Services" means the work described in Schedule A.

2. Payment Terms
The Client shall pay all invoices within ninety (90) days of receipt.

3. Confidentiality
Each party shall keep the other's information confidential for five years.

4.1 Termination for Convenience
Either party may terminate on thirty (30) days written notice.
"""

ARTICLE_CONTRACT = """ARTICLE I Scope
The Supplier shall provide the goods described herein.

ARTICLE II Warranties
The Supplier warrants the goods for twelve months.

SECTION 3 Governing Law
This agreement is governed by the laws of the stated jurisdiction.
"""

UNSTRUCTURED_CONTRACT = """This letter agreement sets out the terms on which we will engage you.
You will invoice monthly and we will settle within sixty days. You agree to keep our
information confidential. Either of us may end this arrangement with a month's notice.
"""


def _pages(text: str, page: int = 1) -> list[tuple[int, str]]:
    """Wrap raw text as a single page."""
    return [(page, text)]


# --------------------------------------------------------------------------- structural path


def test_numbered_clauses_yield_gold_count() -> None:
    """A conventionally numbered contract segments into exactly the labelled clause count."""
    clauses = segment_structural(_pages(DECIMAL_CONTRACT))
    assert len(clauses) == 4
    assert [clause.clause_index for clause in clauses] == [0, 1, 2, 3]


def test_article_and_section_headings_are_recognised() -> None:
    """ARTICLE and SECTION numbering are as common as decimal numbering in real contracts."""
    clauses = segment_structural(_pages(ARTICLE_CONTRACT))
    assert len(clauses) == 3


def test_headings_preserved_verbatim() -> None:
    """Clause headings survive segmentation unchanged, so gold alignment by heading works."""
    headings = [clause.heading for clause in segment_structural(_pages(DECIMAL_CONTRACT))]
    assert headings == [
        "1. Definitions",
        "2. Payment Terms",
        "3. Confidentiality",
        "4.1 Termination for Convenience",
    ]


def test_clause_body_follows_its_heading() -> None:
    """Body text lands under the right heading.

    Otherwise every verdict is judged against the wrong clause.
    """
    clauses = segment_structural(_pages(DECIMAL_CONTRACT))
    payment = next(clause for clause in clauses if clause.heading.startswith("2."))
    assert "ninety (90) days" in payment.text
    assert "confidential" not in payment.text.lower()


def test_preamble_before_the_first_heading_is_not_a_clause() -> None:
    """Front matter is not a contractual clause and must not be scored as one."""
    clauses = segment_structural(_pages(DECIMAL_CONTRACT))
    assert not any("MASTER SERVICES AGREEMENT" in clause.text for clause in clauses)


def test_clause_spanning_pages_keeps_start_page() -> None:
    """A clause crossing a page boundary reports the page where it starts (ADR-012)."""
    pages = [
        (4, "2. Payment Terms\nThe Client shall pay all invoices"),
        (5, "within ninety (90) days of receipt."),
    ]
    clauses = segment_structural(pages)
    assert len(clauses) == 1
    assert clauses[0].page == 4
    assert "ninety (90) days" in clauses[0].text


def test_structural_clauses_are_labelled_with_their_path() -> None:
    """segmentation_path drives the eval's fallback-coverage check."""
    for clause in segment_structural(_pages(DECIMAL_CONTRACT)):
        assert clause.segmentation_path == STRUCTURAL


# --------------------------------------------------------------------------- fallback trigger


def test_fallback_triggers_when_structure_is_absent() -> None:
    """Fewer than two structural clauses means the structural pass did not work (ADR-009)."""
    assert should_use_fallback(segment_structural(_pages(UNSTRUCTURED_CONTRACT))) is True


def test_fallback_triggers_on_an_oversized_blob() -> None:
    """One heading matching while the rest lands in a single blob is the common failure."""
    blob = Clause(
        clause_index=0,
        heading="1. Everything",
        text="x" * 5000,
        page=1,
        segmentation_path=STRUCTURAL,
    )
    other = Clause(0, "2. Other", "short", 1, STRUCTURAL)
    assert should_use_fallback([blob, other]) is True


def test_good_structure_does_not_trigger_the_fallback() -> None:
    """The deterministic path is preferred whenever it works; the LLM is the exception."""
    assert should_use_fallback(segment_structural(_pages(DECIMAL_CONTRACT))) is False


def test_unstructured_contract_routes_to_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """A contract without usable numbering is segmented via the LLM path and labelled as such."""
    monkeypatch.setattr(
        segmentation,
        "complete_json",
        lambda *args, **kwargs: {
            "clauses": [
                {
                    "heading": "Payment",
                    "text": "You will invoice monthly and we will settle within sixty days.",
                },
                {
                    "heading": "Confidentiality",
                    "text": "You agree to keep our information confidential.",
                },
            ]
        },
    )

    clauses = segment_contract(_pages(UNSTRUCTURED_CONTRACT))

    assert len(clauses) == 2
    assert all(clause.segmentation_path == LLM_FALLBACK for clause in clauses)


def test_fallback_failure_degrades_rather_than_crashes(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the LLM fallback fails, return what structure we found instead of raising."""
    from app.generation.llm import LLMError

    def boom(*args: object, **kwargs: object) -> dict:
        raise LLMError("model unavailable")

    monkeypatch.setattr(segmentation, "complete_json", boom)
    clauses = segment_contract(_pages(UNSTRUCTURED_CONTRACT))
    assert isinstance(clauses, list)  # empty is acceptable; an exception is not


# --------------------------------------------------------------------------- edge cases


def test_empty_contract_returns_no_clauses() -> None:
    """An empty or unparseable contract returns zero clauses rather than raising."""
    assert segment_contract([]) == []
    assert segment_structural([(1, "")]) == []


def test_a_long_line_is_not_mistaken_for_a_heading() -> None:
    """Headings are short; a numbered sentence in a paragraph must not split the clause."""
    text = "1. Definitions\n" + "2. " + ("word " * 100)
    clauses = segment_structural(_pages(text))
    assert len(clauses) == 1
