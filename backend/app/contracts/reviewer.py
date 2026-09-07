"""Per-clause compliance review against the internal policy corpus.

For each clause: retrieve policy through the same permission-filtered engine the chat surface
uses, compare, and emit a verdict with a citation. Output is decision support, not legal advice,
and that label is attached here so every exit point inherits it (ADR-010).
"""

from dataclasses import dataclass
from enum import Enum

from app.auth import Identity
from app.contracts.segmentation import Clause

LEGAL_DISCLAIMER = (
    "Automated decision support only. This is not legal advice and does not replace review "
    "by a qualified legal professional."
)


class Verdict(str, Enum):
    """The four allowed clause verdicts. No other value may be returned."""

    COMPLIANT = "Compliant"
    DEVIATES = "Deviates"
    MISSING = "Missing"
    NEEDS_LEGAL_REVIEW = "Needs Legal Review"


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


def review_contract(
    contract_path: str,
    contract_name: str,
    identity: Identity,
) -> ContractReviewResult:
    """Parse, segment, and review a contract clause by clause as a specific caller."""
    raise NotImplementedError


def review_clause(clause: Clause, identity: Identity) -> ClauseReview:
    """Retrieve relevant policy for one clause and produce its verdict."""
    raise NotImplementedError


def validate_upload(filename: str, size_bytes: int, mime_type: str) -> None:
    """Reject uploads that violate the configured type and size limits.

    Raises:
        InvalidUploadError: On a disallowed MIME type or an oversized file.
    """
    raise NotImplementedError


class InvalidUploadError(Exception):
    """Raised when an uploaded contract fails validation."""


# TODO:
#  1. Implement validate_upload() against contract_allowed_mime_types and contract_max_upload_mb,
#     checking the sniffed type rather than trusting the extension. Test both rejection paths.
#  2. Implement review_clause(): retrieve from policy_collection via RetrievalEngine with the
#     caller identity -- never a service identity, never an unfiltered search.
#  3. Map an insufficient-evidence retrieval to Verdict.MISSING or NEEDS_LEGAL_REVIEW, decide
#     which, and write the rule down. Never let a clause silently come back Compliant because
#     nothing was retrieved.
#  4. Constrain the LLM reply to the Verdict enum; treat an out-of-vocabulary label as an error.
#  5. Implement review_contract() and persist ContractReview and ClauseVerdict rows.
#  6. Attach LEGAL_DISCLAIMER to every result, and test that it survives serialisation through
#     the API response and the MCP tool result, not just the UI.
#  7. Handle the no-matching-policy case explicitly; it is a listed Sprint 4 edge case.
