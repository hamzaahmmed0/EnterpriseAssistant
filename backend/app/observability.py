"""Structured logging at the pipeline boundaries.

These logs are an evaluation artifact, not debug noise: the access-control audit trail and the
adaptive-loop retry statistics in docs/EVALUATION.md are both derived from them. Nothing logged
here may contain restricted chunk text -- only ids, counts, and scores.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

LOGGER_NAME = "eka"
_logger = logging.getLogger(LOGGER_NAME)

#: Correlation id for the request currently being served. Every log line carries it.
_query_id: ContextVar[str] = ContextVar("query_id", default="-")

#: Fields that must never be logged, however convenient. Enforced by _emit.
_FORBIDDEN_KEYS = frozenset({"text", "chunk_text", "answer", "content", "context", "clause_text"})


class _JsonFormatter(logging.Formatter):
    """One JSON object per line, so eval/ can parse the log without a regex."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "query_id": getattr(record, "query_id", "-"),
        }
        payload.update(getattr(record, "fields", {}))
        return json.dumps(payload, default=str)


def configure_logging(log_level: str = "INFO") -> None:
    """Install the process-wide structured logging configuration."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter())
    _logger.handlers = [handler]
    _logger.setLevel(log_level.upper())
    _logger.propagate = False


def new_query_id() -> str:
    """Mint and install a correlation id for the current request."""
    qid = uuid.uuid4().hex[:12]
    _query_id.set(qid)
    return qid


def current_query_id() -> str:
    """Return the correlation id for the current request, or "-" outside one."""
    return _query_id.get()


def _emit(event: str, **fields: Any) -> None:
    """Emit one structured event, refusing to log document or answer text."""
    leaked = _FORBIDDEN_KEYS.intersection(fields)
    if leaked:
        raise ValueError(f"refusing to log content fields: {sorted(leaked)}")
    _logger.info(event, extra={"query_id": current_query_id(), "fields": fields})


def log_access_decision(
    *,
    user_id: str,
    department: str,
    access_level: str,
    applied_filter: dict[str, Any],
    collection: str,
    outcome: str,
    result_count: int,
) -> None:
    """Record which access filter was applied to a search and what it let through.

    Args:
        user_id: Authenticated caller.
        department: Department used to build the filter.
        access_level: Access level used to build the filter.
        applied_filter: The serialised Qdrant filter actually passed to search().
        collection: Qdrant collection searched.
        outcome: "allow" or "deny".
        result_count: Number of chunks returned after the pre-filter.

    Raises:
        ValueError: If applied_filter is empty. An unfiltered search must be impossible to log,
            because it must be impossible to make.
    """
    if not applied_filter:
        raise ValueError("access decision logged with an empty filter -- search was unfiltered")
    _emit(
        "access_decision",
        user_id=user_id,
        department=department,
        access_level=access_level,
        applied_filter=applied_filter,
        collection=collection,
        outcome=outcome,
        result_count=result_count,
    )


def log_retrieval_attempt(
    *,
    attempt: int,
    query_chars: int,
    evidence_score: float,
    threshold: float,
    decision: str,
    chunk_count: int,
    latency_seconds: float,
) -> None:
    """Record one pass of the adaptive loop.

    Args:
        attempt: 1-based attempt number.
        query_chars: Length of the query used on this attempt. The query itself is not logged --
            a reformulated query can quote restricted content back at us.
        evidence_score: Score assigned to the retrieved evidence.
        threshold: The configured threshold it was compared against.
        decision: "generate", "retry", or "insufficient_evidence".
        chunk_count: Chunks retrieved on this attempt.
        latency_seconds: Wall-clock time for this attempt.
    """
    _emit(
        "retrieval_attempt",
        attempt=attempt,
        query_chars=query_chars,
        evidence_score=round(evidence_score, 4),
        threshold=threshold,
        decision=decision,
        chunk_count=chunk_count,
        latency_seconds=round(latency_seconds, 3),
    )


def log_generation(
    *,
    model: str,
    purpose: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_seconds: float,
    citation_count: int = 0,
) -> None:
    """Record one LLM call, for cost and latency reporting.

    Args:
        model: Model tag actually used.
        purpose: "answer", "judge", "reformulate", "verdict", or "segment".
        prompt_tokens: Prompt token count reported by the server.
        completion_tokens: Completion token count reported by the server.
        latency_seconds: Wall-clock time for the call.
        citation_count: Citations extracted, for answer calls.
    """
    _emit(
        "generation",
        model=model,
        purpose=purpose,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_seconds=round(latency_seconds, 3),
        citation_count=citation_count,
    )


def log_error(event: str, **fields: Any) -> None:
    """Record a failure at a pipeline boundary (ingestion, retrieval, generation)."""
    _logger.error(event, extra={"query_id": current_query_id(), "fields": fields})
