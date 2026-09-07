"""Evidence scoring: does the retrieved context actually support an answer?

The score produced here drives the adaptive loop and is logged for every attempt, so its
definition is part of the experimental method, not an implementation detail (ADR-004).
"""

from app.retrieval.vector_store import RetrievedChunk


def score_evidence(query: str, chunks: list[RetrievedChunk]) -> float:
    """Score how well the retrieved chunks support answering the query.

    Args:
        query: The query used for this retrieval attempt.
        chunks: Chunks returned by the filtered search, highest scoring first.

    Returns:
        A score in [0, 1], comparable across queries and across configurations.
    """
    raise NotImplementedError


def is_sufficient(score: float, threshold: float) -> bool:
    """Return whether the evidence clears the configured threshold."""
    raise NotImplementedError


# TODO:
#  1. Resolve ADR-004 open question 1 (mean top-k similarity vs. max vs. score gap vs. LLM judge)
#     and record the choice with its latency cost before implementing score_evidence().
#  2. Implement score_evidence() so it is defined for the empty-chunks case: zero, not an error.
#  3. Normalise to [0, 1] so a threshold calibrated once stays meaningful across queries.
#  4. Implement is_sufficient() as a single comparison; nothing else may compare to the threshold.
#  5. Add a unit test pinning the score for a fixed synthetic chunk list -- the sweep table in
#     docs/EVALUATION.md is meaningless if the scoring function drifts between runs.
#  6. Expose the score in the API response so the UI and eval harness read the same number.
