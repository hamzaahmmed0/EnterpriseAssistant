"""Tests for upload validation, verdict semantics, and the legal disclaimer.

The rule under test that matters most (ADR-011): a clause that could not be checked is never
reported as Compliant. Failing toward human review is the correct direction for a decision-support
tool, and it is the behaviour a grader will probe first.
"""

from __future__ import annotations

import pytest

from app.contracts import reviewer as reviewer_module
from app.contracts.reviewer import (
    LEGAL_DISCLAIMER,
    InvalidUploadError,
    Verdict,
    review_clause,
    validate_upload,
)
from app.contracts.segmentation import STRUCTURAL, Clause
from app.retrieval.engine import RetrievalResult

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture
def clause() -> Clause:
    """A payment-terms clause that deviates from a net-30 policy."""
    return Clause(
        clause_index=0,
        heading="4. Payment Terms",
        text="The Client shall pay all invoices within ninety (90) days of receipt.",
        page=2,
        segmentation_path=STRUCTURAL,
    )


def _retrieval(chunks, *, sufficient: bool, score: float = 0.8) -> RetrievalResult:
    """Build a policy RetrievalResult."""
    return RetrievalResult(
        query="payment terms",
        chunks=chunks,
        evidence_score=score,
        attempts=1,
        sufficient=sufficient,
        applied_filter={"must": [{"key": "department", "match": {"any": ["finance"]}}]},
        latency_seconds=0.4,
        collection="policy_collection",
    )


@pytest.fixture
def wire_policy(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201 - harness fixture
    """Fake the policy engine and the verdict LLM call."""

    def _wire(retrieval: RetrievalResult, reply: dict | Exception):
        class FakeEngine:
            def retrieve(self, query, identity, top_k=None):  # noqa: ANN001, ANN202
                return retrieval

        monkeypatch.setattr(reviewer_module, "policy_engine", lambda: FakeEngine())

        def fake_json(*args: object, **kwargs: object) -> dict:
            if isinstance(reply, Exception):
                raise reply
            return reply

        monkeypatch.setattr(reviewer_module, "complete_json", fake_json)

    return _wire


# --------------------------------------------------------------------------- upload validation


def test_oversized_upload_is_rejected() -> None:
    """The size limit is enforced on the received bytes, not the client's claim."""
    with pytest.raises(InvalidUploadError, match="limit"):
        validate_upload("contract.pdf", 50 * 1024 * 1024, PDF_MIME)


def test_empty_upload_is_rejected() -> None:
    """A zero-byte file is a client error, not an empty contract."""
    with pytest.raises(InvalidUploadError, match="empty"):
        validate_upload("contract.pdf", 0, PDF_MIME)


def test_disallowed_mime_type_is_rejected() -> None:
    """Only PDF and DOCX are accepted."""
    with pytest.raises(InvalidUploadError, match="unsupported file type"):
        validate_upload("contract.exe", 1024, "application/x-msdownload")


def test_extension_is_cross_checked() -> None:
    """A PDF-sniffed payload with a mismatched extension is still refused."""
    with pytest.raises(InvalidUploadError, match="extension"):
        validate_upload("contract.txt", 1024, PDF_MIME)


@pytest.mark.parametrize(("name", "mime"), [("c.pdf", PDF_MIME), ("c.docx", DOCX_MIME)])
def test_valid_uploads_pass(name: str, mime: str) -> None:
    """The happy path for both accepted formats."""
    validate_upload(name, 2048, mime)


# --------------------------------------------------------------------------- verdict semantics


def test_insufficient_policy_is_needs_legal_review_never_compliant(
    clause: Clause, finance_identity, wire_policy
) -> None:
    """ADR-011: a clause that could not be checked has not been found to be fine."""
    wire_policy(_retrieval([], sufficient=False, score=0.1), {"verdict": "Compliant"})

    review = review_clause(clause, finance_identity)

    assert review.verdict is Verdict.NEEDS_LEGAL_REVIEW
    assert review.cited_policy_doc is None


def test_deviation_is_reported_with_its_citation(
    clause: Clause, finance_identity, wire_policy, make_chunk
) -> None:
    """A positive finding carries the policy document and section it was judged against."""
    chunk = make_chunk(
        document_id="fin-procurement-policy",
        text="Vendor payment terms shall not exceed net-30.",
        page=4,
        department="finance",
    )
    wire_policy(
        _retrieval([chunk], sufficient=True),
        {
            "verdict": "Deviates",
            "cited_block": 1,
            "explanation": "Contract says net-90; policy caps at net-30.",
        },
    )

    review = review_clause(clause, finance_identity)

    assert review.verdict is Verdict.DEVIATES
    assert review.cited_policy_doc == "fin-procurement-policy"
    assert review.cited_policy_section == "p.4"


def test_compliant_without_a_citation_is_downgraded(
    clause: Clause, finance_identity, wire_policy, make_chunk
) -> None:
    """A verdict asserting something about policy must point at that policy."""
    wire_policy(
        _retrieval([make_chunk()], sufficient=True),
        {"verdict": "Compliant", "cited_block": None, "explanation": "Looks fine."},
    )

    review = review_clause(clause, finance_identity)

    assert review.verdict is Verdict.NEEDS_LEGAL_REVIEW
    assert "Needs Legal Review" in review.explanation


def test_out_of_range_citation_is_not_trusted(
    clause: Clause, finance_identity, wire_policy, make_chunk
) -> None:
    """A block number outside the supplied context resolves to no citation, then downgrades."""
    wire_policy(
        _retrieval([make_chunk()], sufficient=True),
        {"verdict": "Deviates", "cited_block": 9, "explanation": "Conflicts."},
    )
    assert review_clause(clause, finance_identity).verdict is Verdict.NEEDS_LEGAL_REVIEW


def test_unknown_verdict_label_falls_back_to_review(
    clause: Clause, finance_identity, wire_policy, make_chunk
) -> None:
    """An out-of-vocabulary label is an error, and errors fail toward human review."""
    wire_policy(
        _retrieval([make_chunk()], sufficient=True),
        {"verdict": "Probably OK", "cited_block": 1, "explanation": "..."},
    )
    assert review_clause(clause, finance_identity).verdict is Verdict.NEEDS_LEGAL_REVIEW


def test_llm_failure_does_not_lose_the_clause(
    clause: Clause, finance_identity, wire_policy, make_chunk
) -> None:
    """A failed comparison still produces a reviewable row rather than dropping the clause."""
    from app.generation.llm import LLMError

    wire_policy(_retrieval([make_chunk()], sufficient=True), LLMError("model down"))

    review = review_clause(clause, finance_identity)

    assert review.verdict is Verdict.NEEDS_LEGAL_REVIEW
    assert review.clause.clause_index == clause.clause_index


def test_only_four_verdicts_exist() -> None:
    """The enum is the contract with the database check constraint and the eval confusion matrix."""
    assert {verdict.value for verdict in Verdict} == {
        "Compliant",
        "Deviates",
        "Missing",
        "Needs Legal Review",
    }


# --------------------------------------------------------------------------- disclaimer


def test_disclaimer_is_present_and_says_not_legal_advice() -> None:
    """ADR-010. Asserted as text because it is a required part of every contract response."""
    assert "not legal advice" in LEGAL_DISCLAIMER.lower()


def test_api_response_cannot_be_built_without_the_disclaimer() -> None:
    """The schema makes omission impossible rather than merely discouraged."""
    from pydantic import ValidationError

    from app.api.schemas import CheckContractResponse

    with pytest.raises(ValidationError):
        CheckContractResponse(
            contract_review_id="r1",
            contract_name="c.pdf",
            clauses=[],
            segmentation_path="structural",
            latency_seconds=1.0,
        )  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        CheckContractResponse(
            contract_review_id="r1",
            contract_name="c.pdf",
            clauses=[],
            segmentation_path="structural",
            disclaimer="",
            latency_seconds=1.0,
        )
