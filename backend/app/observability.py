"""Structured logging at the pipeline boundaries.

These logs are an evaluation artifact, not debug noise: the access-control audit trail and the
adaptive-loop retry statistics in docs/EVALUATION.md are both derived from them. Nothing logged
here may contain restricted chunk text.
"""

from typing import Any


def configure_logging(log_level: str) -> None:
    """Install the process-wide structured logging configuration."""
    raise NotImplementedError


def log_access_decision(
    *,
    query_id: str,
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
        query_id: Correlation id shared by every log line for one user request.
        user_id: Authenticated caller.
        department: Department used to build the filter.
        access_level: Access level used to build the filter.
        applied_filter: The serialised Qdrant filter actually passed to search().
        collection: Qdrant collection searched.
        outcome: "allow" or "deny".
        result_count: Number of chunks returned after the pre-filter.
    """
    raise NotImplementedError


def log_retrieval_attempt(
    *,
    query_id: str,
    attempt: int,
    query_text: str,
    evidence_score: float,
    threshold: float,
    decision: str,
    latency_seconds: float,
) -> None:
    """Record one pass of the adaptive loop.

    Args:
        query_id: Correlation id shared by every attempt for one user request.
        attempt: 1-based attempt number.
        query_text: Query used on this attempt (reformulated after attempt 1).
        evidence_score: Score assigned to the retrieved evidence.
        threshold: Configured threshold it was compared against.
        decision: "generate", "retry", or "insufficient_evidence".
        latency_seconds: Wall-clock time for this attempt.
    """
    raise NotImplementedError


def log_generation(
    *,
    query_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_seconds: float,
    citation_count: int,
) -> None:
    """Record one LLM generation call, for cost and latency reporting."""
    raise NotImplementedError


# TODO:
#  1. Implement configure_logging(): JSON lines to stdout, one event per line, ISO-8601 stamps.
#  2. Mint a query_id per request in middleware and thread it through all four log calls.
#  3. Implement log_access_decision(), and assert applied_filter is non-empty at call time --
#     an unfiltered search must be impossible to log because it must be impossible to make.
#  4. Implement log_retrieval_attempt() and log_generation().
#  5. Add a redaction guard: chunk text and answer text are never logged, only ids and counts.
#  6. Write the reader in eval/ that turns these lines into the retry-count and access-control
#     tables in docs/EVALUATION.md.
