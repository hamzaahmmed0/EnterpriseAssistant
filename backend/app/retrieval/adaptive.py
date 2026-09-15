"""The bounded adaptive retrieval loop (LangGraph).

retrieve -> judge -> (reformulate -> retry, hard-capped) -> generate | insufficient evidence.

Two invariants, both tested:

1. The loop always terminates within ``settings.adaptive_max_attempts``. The cap is checked in
   ``route_after_score`` and nowhere else.
2. The "insufficient evidence" exit is a first-class output, not an error path (ADR-004).

The access filter is re-applied on every attempt: a retry widens the *query*, never the caller's
visibility.
"""

from __future__ import annotations

import time
from typing import Any, Literal, TypedDict

from app.auth import Identity
from app.config import get_settings
from app.generation import prompts
from app.generation.llm import LLMError, complete
from app.observability import log_retrieval_attempt
from app.retrieval.engine import RetrievalEngine, RetrievalResult
from app.retrieval.scoring import evaluate_evidence, is_sufficient
from app.retrieval.vector_store import RetrievedChunk

Decision = Literal["generate", "retry", "insufficient_evidence"]


class AdaptiveState(TypedDict, total=False):
    """State carried between nodes of the adaptive graph."""

    original_query: str
    current_query: str
    identity: Identity
    collection: str
    top_k: int | None
    attempt: int
    chunks: list[RetrievedChunk]
    applied_filter: dict[str, Any]
    evidence_score: float
    missing: str
    decision: Decision
    queries_tried: list[str]
    started: float


# --------------------------------------------------------------------------- nodes


def node_retrieve(state: AdaptiveState) -> AdaptiveState:
    """Run one filtered retrieval for the current query.

    Delegates to RetrievalEngine.retrieve_fixed with judging disabled: the loop scores in
    node_score, and the engine must not be asked to pay for the judge twice.
    """
    engine = RetrievalEngine(state["collection"])
    attempt_started = time.perf_counter()

    result = engine.retrieve_fixed(
        state["current_query"],
        state["identity"],
        state.get("top_k"),
        judge=False,
    )

    queries = list(state.get("queries_tried", []))
    if state["current_query"] not in queries:
        queries.append(state["current_query"])

    return {
        **state,
        "attempt": state.get("attempt", 0) + 1,
        "chunks": result.chunks,
        "applied_filter": result.applied_filter,
        "queries_tried": queries,
        "started": attempt_started,
    }


def node_score(state: AdaptiveState) -> AdaptiveState:
    """Judge the retrieved evidence and record the attempt."""
    settings = get_settings()
    judgement = evaluate_evidence(state["original_query"], state.get("chunks", []))
    sufficient = is_sufficient(judgement.score, settings.evidence_threshold)

    at_cap = state["attempt"] >= settings.adaptive_max_attempts
    decision: Decision = (
        "generate" if sufficient else ("insufficient_evidence" if at_cap else "retry")
    )

    log_retrieval_attempt(
        attempt=state["attempt"],
        query_chars=len(state["current_query"]),
        evidence_score=judgement.score,
        threshold=settings.evidence_threshold,
        decision=decision,
        chunk_count=len(state.get("chunks", [])),
        latency_seconds=time.perf_counter() - state.get("started", time.perf_counter()),
    )

    return {
        **state,
        "evidence_score": judgement.score,
        "missing": judgement.missing,
        "decision": decision,
    }


def node_reformulate(state: AdaptiveState) -> AdaptiveState:
    """Produce a new query for the next attempt, targeting what the judge said was missing.

    If the rewrite fails or returns something unusable, the previous query is reused. That
    wastes one attempt rather than crashing the request, and the cap still bounds the loop.
    """
    try:
        reply = complete(
            prompts.reformulation_prompt(
                state["original_query"],
                state["current_query"],
                state.get("missing", ""),
            ),
            purpose="reformulate",
        )
        rewritten = reply.text.strip().strip('"').splitlines()[0].strip() if reply.text else ""
    except LLMError:
        rewritten = ""

    if not rewritten or len(rewritten) < 3:
        rewritten = state["current_query"]

    return {**state, "current_query": rewritten}


def route_after_score(state: AdaptiveState) -> Decision:
    """Choose the next step: "generate", "retry", or "insufficient_evidence".

    The cap is checked here and nowhere else: once ``attempt`` reaches
    ``settings.adaptive_max_attempts`` the answer is "insufficient_evidence" regardless of score.
    """
    return state.get("decision", "insufficient_evidence")


# --------------------------------------------------------------------------- graph


def build_adaptive_graph() -> Any:
    """Compile the LangGraph state machine for adaptive retrieval.

    Falls back to the equivalent hand-rolled loop in ``_run_without_langgraph`` if langgraph is
    not installed, so the engine stays usable (and testable) without it. The topology is
    identical; only the executor differs.
    """
    from langgraph.graph import END, StateGraph

    graph = StateGraph(AdaptiveState)
    graph.add_node("retrieve", node_retrieve)
    graph.add_node("score", node_score)
    graph.add_node("reformulate", node_reformulate)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "score")
    graph.add_conditional_edges(
        "score",
        route_after_score,
        {"generate": END, "insufficient_evidence": END, "retry": "reformulate"},
    )
    graph.add_edge("reformulate", "retrieve")
    return graph.compile()


def _run_without_langgraph(state: AdaptiveState) -> AdaptiveState:
    """Execute the same topology as a plain loop, bounded by the same cap."""
    max_attempts = get_settings().adaptive_max_attempts
    while True:
        state = node_score(node_retrieve(state))
        if route_after_score(state) != "retry":
            return state
        if state["attempt"] >= max_attempts:  # belt and braces; node_score already decided
            return {**state, "decision": "insufficient_evidence"}
        state = node_reformulate(state)


def run_adaptive_retrieval(
    query: str,
    identity: Identity,
    collection: str,
    top_k: int | None = None,
) -> RetrievalResult:
    """Execute the adaptive loop and return the final retrieval result."""
    started = time.perf_counter()
    initial: AdaptiveState = {
        "original_query": query,
        "current_query": query,
        "identity": identity,
        "collection": collection,
        "top_k": top_k,
        "attempt": 0,
        "chunks": [],
        "applied_filter": {},
        "evidence_score": 0.0,
        "missing": "",
        "queries_tried": [],
    }

    try:
        final: AdaptiveState = build_adaptive_graph().invoke(initial)
    except ImportError:
        final = _run_without_langgraph(initial)

    return RetrievalResult(
        query=query,
        chunks=final.get("chunks", []),
        evidence_score=final.get("evidence_score", 0.0),
        attempts=final.get("attempt", 0),
        sufficient=final.get("decision") == "generate",
        applied_filter=final.get("applied_filter", {}),
        latency_seconds=time.perf_counter() - started,
        collection=collection,
        missing=final.get("missing", ""),
        queries_tried=final.get("queries_tried", []),
    )
