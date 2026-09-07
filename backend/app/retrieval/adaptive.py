"""The bounded adaptive retrieval loop (LangGraph).

retrieve -> score -> (reformulate -> retry, hard-capped) -> generate | insufficient evidence.

Two invariants: the loop always terminates within settings.adaptive_max_attempts, and the
"insufficient evidence" exit is a first-class, tested output rather than an error path (ADR-004).
"""

from typing import Any, TypedDict

from app.auth import Identity
from app.retrieval.engine import RetrievalResult


class AdaptiveState(TypedDict):
    """State carried between nodes of the adaptive graph."""

    original_query: str
    current_query: str
    identity: Identity
    attempt: int
    chunks: list[Any]
    evidence_score: float
    decision: str


def node_retrieve(state: AdaptiveState) -> AdaptiveState:
    """Run one filtered retrieval for the current query."""
    raise NotImplementedError


def node_score(state: AdaptiveState) -> AdaptiveState:
    """Score the retrieved evidence and record the attempt."""
    raise NotImplementedError


def node_reformulate(state: AdaptiveState) -> AdaptiveState:
    """Produce a new query for the next attempt."""
    raise NotImplementedError


def route_after_score(state: AdaptiveState) -> str:
    """Choose the next node: "generate", "reformulate", or "insufficient_evidence".

    Returns "insufficient_evidence" once attempt reaches settings.adaptive_max_attempts,
    regardless of score. The cap is checked here and nowhere else.
    """
    raise NotImplementedError


def build_adaptive_graph() -> Any:
    """Compile the LangGraph state machine for adaptive retrieval."""
    raise NotImplementedError


def run_adaptive_retrieval(query: str, identity: Identity, collection: str) -> RetrievalResult:
    """Execute the adaptive loop and return the final retrieval result."""
    raise NotImplementedError


# TODO:
#  1. Resolve ADR-004 open questions 3 and 4 (cap of 2 or 3; what reformulation actually does)
#     before wiring the graph.
#  2. Implement node_retrieve() delegating to RetrievalEngine.retrieve_fixed -- the loop reuses
#     the filtered path, it does not open its own search.
#  3. Implement node_score() and emit log_retrieval_attempt() from it, once per attempt.
#  4. Implement route_after_score() with the cap checked first, score second.
#  5. Implement node_reformulate(); whatever it does, the access filter still applies to the
#     retry, and a widened top_k is still k authorized chunks.
#  6. Implement build_adaptive_graph() and run_adaptive_retrieval().
#  7. Test: a query engineered to score below threshold terminates after exactly max_attempts and
#     returns sufficient=False. Assert the attempt count, not just the outcome.
#  8. Test: a query that clears the threshold on attempt 1 never invokes node_reformulate.
#  9. Record attempts on RetrievalResult so the mean-retry-count row in docs/EVALUATION.md can be
#     computed without parsing logs.
