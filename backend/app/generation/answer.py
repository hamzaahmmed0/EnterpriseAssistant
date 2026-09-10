"""Grounded answer assembly.

Takes a RetrievalResult and produces either a cited answer built only from that context, or the
insufficient-evidence output. There is no third case, and parametric knowledge is never a source.

The exact fallback wording is part of the API contract (ADR-004) and is pinned by a test.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from app.generation import prompts
from app.generation.llm import LLMError, complete
from app.observability import log_error
from app.retrieval.engine import RetrievalResult

#: The honest exit. Returned whenever evidence is insufficient, never replaced by a guess.
INSUFFICIENT_EVIDENCE_MESSAGE = (
    "I could not find enough evidence in the documents you have access to answer this question. "
    "This may mean the information is not in the corpus, or that it lives in a document your "
    "role cannot read."
)

#: Sentinel the answer prompt instructs the model to emit when the context is not enough.
_MODEL_INSUFFICIENT_SENTINEL = "INSUFFICIENT_EVIDENCE"

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


class UngroundedCitationError(Exception):
    """Raised when a generated citation does not correspond to supplied context."""


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


def generate_answer(
    question: str,
    retrieval: RetrievalResult,
    titles: dict[str, str] | None = None,
) -> Answer:
    """Generate a cited answer from retrieved context, or return the fallback.

    Args:
        question: The user question, unmodified.
        retrieval: Evidence from the permission-filtered engine.
        titles: Optional document_id -> title map, from the relational store. Missing titles
            fall back to the document id so a citation is never blank.

    Returns:
        An Answer. When ``retrieval.sufficient`` is False this is the insufficient-evidence
        output with an empty citation list -- not an error.
    """
    if not retrieval.sufficient or not retrieval.chunks:
        # Short-circuit: no LLM call at all, so no parametric answer can leak in.
        return insufficient_evidence_answer(retrieval)

    started = time.perf_counter()
    try:
        response = complete(
            prompts.answer_user_prompt(question, [chunk.text for chunk in retrieval.chunks]),
            prompts.answer_system_prompt(),
            purpose="answer",
        )
    except LLMError as exc:
        log_error("generation_failed", error=str(exc))
        return insufficient_evidence_answer(retrieval)

    text = response.text.strip()
    if not text or _MODEL_INSUFFICIENT_SENTINEL in text.upper():
        return insufficient_evidence_answer(retrieval)

    citations = extract_citations(text, retrieval, titles or {})
    if not citations:
        # Citation is required (CLAUDE.md non-negotiable 3). An uncited answer is a failure,
        # not a partial success, so it is reported as insufficient rather than shown.
        log_error("uncited_answer_rejected", chunk_count=len(retrieval.chunks))
        return insufficient_evidence_answer(retrieval)

    return Answer(
        text=text,
        citations=citations,
        sufficient=True,
        evidence_score=retrieval.evidence_score,
        attempts=retrieval.attempts,
        latency_seconds=retrieval.latency_seconds + (time.perf_counter() - started),
    )


def insufficient_evidence_answer(retrieval: RetrievalResult) -> Answer:
    """Build the standard insufficient-evidence response.

    A first-class output with its own tests: the wording is part of the API contract.
    """
    return Answer(
        text=INSUFFICIENT_EVIDENCE_MESSAGE,
        citations=[],
        sufficient=False,
        evidence_score=retrieval.evidence_score,
        attempts=retrieval.attempts,
        latency_seconds=retrieval.latency_seconds,
    )


def extract_citations(
    llm_text: str,
    retrieval: RetrievalResult,
    titles: dict[str, str] | None = None,
) -> list[Citation]:
    """Map the ``[n]`` block references in a completion back to real chunks.

    Args:
        llm_text: The model's answer.
        retrieval: The retrieval whose chunks were placed in the context, in order.
        titles: Optional document_id -> title map.

    Returns:
        Deduplicated citations in first-mention order.

    Raises:
        UngroundedCitationError: If the model cites a block number that was not in its context.
            Citation validity is a reported metric; an unmatched reference is a failure, not a
            warning to swallow.
    """
    titles = titles or {}
    references = [int(match) for match in _CITATION_PATTERN.findall(llm_text)]
    if not references:
        return []

    seen: set[str] = set()
    citations: list[Citation] = []
    for block in references:
        if not 1 <= block <= len(retrieval.chunks):
            raise UngroundedCitationError(
                f"answer cites block [{block}] but only {len(retrieval.chunks)} blocks were "
                "supplied as context"
            )
        chunk = retrieval.chunks[block - 1]
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        citations.append(
            Citation(
                document_id=chunk.document_id,
                document_title=titles.get(chunk.document_id, chunk.document_id),
                page=chunk.page,
                chunk_id=chunk.chunk_id,
            )
        )
    return citations


def citations_to_payload(citations: list[Citation]) -> list[dict]:
    """Serialise citations once, for both the API response and the messages.citations column.

    One definition, so persisted history and live answers cannot drift (ADR-012).
    """
    return [
        {
            "document_id": citation.document_id,
            "document_title": citation.document_title,
            "page": citation.page,
            "chunk_id": citation.chunk_id,
        }
        for citation in citations
    ]
