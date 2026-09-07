"""Grounded answer assembly.

Takes a RetrievalResult and produces either a cited answer built only from that context, or the
insufficient-evidence output. There is no third case, and parametric knowledge is never a source.
"""

from dataclasses import dataclass

from app.retrieval.engine import RetrievalResult


@dataclass(frozen=True)
class Citation:
    """A pointer from an answer back to the chunk that supports it."""

    document_id: str
    document_title: str
    page: int
    chunk_id: str


@dataclass(frozen=True)
class Answer:
    """A generated answer and everything needed to audit it."""

    text: str
    citations: list[Citation]
    sufficient: bool
    evidence_score: float
    attempts: int
    latency_seconds: float


def generate_answer(question: str, retrieval: RetrievalResult) -> Answer:
    """Generate a cited answer from retrieved context, or return the fallback.

    Args:
        question: The user question, unmodified.
        retrieval: Evidence from the permission-filtered engine.

    Returns:
        An Answer. When retrieval.sufficient is False, this is the insufficient-evidence output
        with an empty citation list, not an error.
    """
    raise NotImplementedError


def insufficient_evidence_answer(retrieval: RetrievalResult) -> Answer:
    """Build the standard insufficient-evidence response.

    A first-class output with its own tests: the wording is effectively part of the API contract.
    """
    raise NotImplementedError


def extract_citations(llm_text: str, retrieval: RetrievalResult) -> list[Citation]:
    """Map the block references in a completion back to real chunks.

    Raises:
        UngroundedCitationError: If the model cites a block that was not in its context.
    """
    raise NotImplementedError


class UngroundedCitationError(Exception):
    """Raised when a generated citation does not correspond to supplied context."""


# TODO:
#  1. Settle the exact insufficient-evidence wording (open question in docs/DECISIONS.md) and
#     pin it with a test before anything depends on the string.
#  2. Implement generate_answer(): short-circuit to the fallback when not sufficient, otherwise
#     build the prompt from retrieval.chunks only.
#  3. Implement extract_citations() and treat an unmatched reference as a failure, not a warning;
#     citation validity is a reported metric in docs/EVALUATION.md.
#  4. Return an answer with zero citations as a failure case too -- citation is required.
#  5. Test: given a RetrievalResult with sufficient=False, no LLM call is made at all.
#  6. Test: an answer whose citations reference a chunk outside its own context raises.
#  7. Keep the API response shape and the messages.citations column shape identical, sourced from
#     one definition, so persisted history and live answers cannot drift.
