"""Per-clause compliance review against the internal policy corpus.

For each clause: retrieve policy through the same permission-filtered engine the chat surface
uses, compare, and emit a verdict with a citation. Output is decision support, not legal advice,
and that label is attached here so every exit point inherits it (ADR-010).

Verdict semantics are fixed by ADR-011. The rule that matters most: a clause whose policy
retrieval returns insufficient evidence is always ``Needs Legal Review`` -- never ``Compliant``,
because a clause that could not be checked has not been found to be fine.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.auth import Identity
from app.config import get_settings
from app.contracts.segmentation import Clause, pages_from_parsed, segment_contract
from app.generation import prompts
from app.generation.llm import LLMError, complete_json
from app.ingestion.parsers import UnsupportedFormatError, parse_document
from app.observability import log_error
from app.retrieval.engine import policy_engine

LEGAL_DISCLAIMER = (
    "Automated decision support only. This is not legal advice and does not replace review "
    "by a qualified legal professional."
)


class InvalidUploadError(Exception):
    """Raised when an uploaded contract fails validation."""


class Verdict(str, Enum):
    """The four allowed clause verdicts (ADR-011). No other value may be returned."""

    COMPLIANT = "Compliant"
    DEVIATES = "Deviates"
    MISSING = "Missing"
    NEEDS_LEGAL_REVIEW = "Needs Legal Review"


#: Verdicts that assert something about a specific policy and therefore require a citation.
_CITATION_REQUIRED = {Verdict.COMPLIANT, Verdict.DEVIATES, Verdict.MISSING}


@dataclass(frozen=True)
class ClauseReview:
    """The verdict for one clause, with the policy it was checked against."""

    clause: Clause
    verdict: Verdict
    cited_policy_doc: str | None
    cited_policy_section: str | None
    explanation: str
    evidence_score: float


@dataclass(frozen=True)
class ContractReviewResult:
    """The full clause-by-clause report for one contract."""

    contract_name: str
    reviews: list[ClauseReview]
    disclaimer: str
    latency_seconds: float
    segmentation_path: str


def validate_upload(filename: str, size_bytes: int, mime_type: str) -> None:
    """Reject uploads that violate the configured type and size limits.

    Args:
        filename: Client-supplied filename, used only for the error message and the extension
            cross-check. Never trusted on its own.
        size_bytes: Actual size of the received bytes.
        mime_type: Content type sniffed from the received bytes, not the client's claim.

    Raises:
        InvalidUploadError: On a disallowed MIME type, an oversized file, or an empty upload.
    """
    settings = get_settings()

    if size_bytes <= 0:
        raise InvalidUploadError("uploaded file is empty")
    if size_bytes > settings.contract_max_upload_bytes:
        raise InvalidUploadError(
            f"file is {size_bytes / 1_048_576:.1f} MB; the limit is "
            f"{settings.contract_max_upload_mb} MB"
        )
    if mime_type not in settings.allowed_mime_types:
        raise InvalidUploadError(
            f"unsupported file type {mime_type!r}; upload a PDF or DOCX contract"
        )

    suffix = Path(filename).suffix.lower()
    if suffix not in (".pdf", ".docx"):
        raise InvalidUploadError(f"unsupported file extension {suffix!r}")


def review_clause(clause: Clause, identity: Identity) -> ClauseReview:
    """Retrieve relevant policy for one clause and produce its verdict.

    Retrieval runs as the *caller*, never a service identity: a reviewer only sees the policy
    their role can read, and the verdict reflects that (ADR-001).
    """
    settings = get_settings()
    retrieval = policy_engine().retrieve(clause.text, identity, top_k=settings.contract_top_k)

    if not retrieval.sufficient or not retrieval.chunks:
        # ADR-011: unable to check is not the same as fine.
        return ClauseReview(
            clause=clause,
            verdict=Verdict.NEEDS_LEGAL_REVIEW,
            cited_policy_doc=None,
            cited_policy_section=None,
            explanation=(
                "No applicable policy was found in the documents available to you, so this "
                "clause could not be checked automatically."
            ),
            evidence_score=retrieval.evidence_score,
        )

    try:
        reply = complete_json(
            prompts.clause_verdict_prompt(clause.text, [chunk.text for chunk in retrieval.chunks]),
            prompts.clause_verdict_system_prompt(),
            purpose="verdict",
        )
    except LLMError as exc:
        log_error("verdict_failed", clause_index=clause.clause_index, error=str(exc))
        return ClauseReview(
            clause=clause,
            verdict=Verdict.NEEDS_LEGAL_REVIEW,
            cited_policy_doc=None,
            cited_policy_section=None,
            explanation="The comparison could not be completed; review this clause manually.",
            evidence_score=retrieval.evidence_score,
        )

    verdict = _coerce_verdict(reply.get("verdict"))
    cited_doc, cited_section = _resolve_citation(reply.get("cited_block"), retrieval.chunks)
    explanation = str(reply.get("explanation", "")).strip()

    if verdict in _CITATION_REQUIRED and not cited_doc:
        # A positive finding without a citation is not a finding. Fail toward human review.
        verdict = Verdict.NEEDS_LEGAL_REVIEW
        explanation = (
            explanation or "The model reached a verdict without citing a policy excerpt."
        ) + " Downgraded to Needs Legal Review because no policy citation was produced."

    return ClauseReview(
        clause=clause,
        verdict=verdict,
        cited_policy_doc=cited_doc,
        cited_policy_section=cited_section,
        explanation=explanation or "No explanation was produced.",
        evidence_score=retrieval.evidence_score,
    )


def _coerce_verdict(raw: object) -> Verdict:
    """Map the model's label onto the enum, treating anything unrecognised as needing review."""
    text = str(raw or "").strip().lower()
    for verdict in Verdict:
        if verdict.value.lower() == text:
            return verdict
    return Verdict.NEEDS_LEGAL_REVIEW


def _resolve_citation(raw_block: object, chunks: list) -> tuple[str | None, str | None]:
    """Map a cited block number back to (document_id, page) from the actual context."""
    try:
        block = int(raw_block)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None, None
    if not 1 <= block <= len(chunks):
        return None, None
    chunk = chunks[block - 1]
    return chunk.document_id, f"p.{chunk.page}"


def review_contract(
    contract_path: str,
    contract_name: str,
    identity: Identity,
) -> ContractReviewResult:
    """Parse, segment, and review a contract clause by clause as a specific caller.

    Raises:
        InvalidUploadError: If the file cannot be parsed at all.
    """
    started = time.perf_counter()

    try:
        pages = parse_document(contract_path)
    except (UnsupportedFormatError, FileNotFoundError) as exc:
        raise InvalidUploadError(str(exc)) from exc

    clauses = segment_contract(pages_from_parsed(pages))
    reviews = [review_clause(clause, identity) for clause in clauses]
    path = clauses[0].segmentation_path if clauses else "none"

    return ContractReviewResult(
        contract_name=contract_name,
        reviews=reviews,
        disclaimer=LEGAL_DISCLAIMER,
        latency_seconds=time.perf_counter() - started,
        segmentation_path=path,
    )
