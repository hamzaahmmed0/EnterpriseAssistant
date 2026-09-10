"""The retrieval engine: the one entry point every consumer uses.

Ask, Check, and the MCP server all call this. It takes an Identity and a query, applies the access
filter, runs the configured retrieval mode, and returns scored evidence. It does not generate
answers, and it does not know what a web request is -- the whole module is importable and usable
without the web layer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.auth import Identity
from app.config import get_settings
from app.ingestion.embedder import embed_query
from app.observability import log_retrieval_attempt
from app.retrieval.access_filter import build_access_filter
from app.retrieval.scoring import is_sufficient, judge_evidence
from app.retrieval.vector_store import RetrievedChunk, search


@dataclass(frozen=True)
class RetrievalResult:
    """The outcome of one retrieval, carrying everything the eval harness needs to score it."""

    query: str
    chunks: list[RetrievedChunk]
    evidence_score: float
    attempts: int
    sufficient: bool
    applied_filter: dict[str, Any]
    latency_seconds: float
    collection: str
    missing: str = ""
    queries_tried: list[str] = field(default_factory=list)


class RetrievalEngine:
    """Permission-aware retrieval over a Qdrant collection."""

    def __init__(self, collection: str | None = None) -> None:
        """Bind the engine to a collection.

        Args:
            collection: Qdrant collection name. Defaults to the documents collection; the
                contract reviewer constructs a second engine bound to the policy collection.
        """
        settings = get_settings()
        self.collection = collection or settings.qdrant_documents_collection

    # ------------------------------------------------------------------ public API

    def retrieve(
        self,
        query: str,
        identity: Identity,
        top_k: int | None = None,
    ) -> RetrievalResult:
        """Retrieve evidence for a query as a specific caller.

        Dispatches on settings.retrieval_mode: "fixed" (Config A), "hybrid_rerank" (Config B),
        or "adaptive" (Config C). The access filter is applied in all three -- it is a property
        of the system, not an experimental variable.

        Args:
            query: Natural-language query.
            identity: Authenticated caller. Not optional; there is no anonymous retrieval.
            top_k: Override for settings.retrieval_top_k, used by the eval sweeps.

        Raises:
            ValueError: If the query is empty.
            NotImplementedError: For retrieval_mode="hybrid_rerank" until a reranker is chosen.
        """
        if not query or not query.strip():
            raise ValueError("query must not be empty")

        mode = get_settings().retrieval_mode
        if mode == "fixed":
            return self.retrieve_fixed(query, identity, top_k)
        if mode == "adaptive":
            from app.retrieval.adaptive import run_adaptive_retrieval  # local: breaks the cycle

            return run_adaptive_retrieval(query, identity, self.collection, top_k)
        if mode == "hybrid_rerank":
            raise NotImplementedError(
                "Config B (hybrid + reranker) needs RERANKER_MODEL chosen first; it is the first "
                "item on the cut list in docs/PLAN.md."
            )
        raise ValueError(f"unknown retrieval_mode {mode!r}")

    def retrieve_fixed(
        self,
        query: str,
        identity: Identity,
        top_k: int | None = None,
        *,
        judge: bool = True,
    ) -> RetrievalResult:
        """Single-shot filtered retrieval with no retry. Config A, the baseline.

        Args:
            query: Natural-language query.
            identity: Authenticated caller.
            top_k: Override for settings.retrieval_top_k.
            judge: Whether to score the evidence. The adaptive loop scores separately, so it
                passes False to avoid paying for the judge twice.
        """
        settings = get_settings()
        started = time.perf_counter()

        chunks, applied_filter = self._search(query, identity, top_k)

        if judge:
            judgement = judge_evidence(query, chunks)
            score, sufficient, missing = (
                judgement.score,
                is_sufficient(judgement.score, settings.evidence_threshold),
                judgement.missing,
            )
        else:
            score, sufficient, missing = 0.0, bool(chunks), ""

        elapsed = time.perf_counter() - started

        if judge:
            log_retrieval_attempt(
                attempt=1,
                query_chars=len(query),
                evidence_score=score,
                threshold=settings.evidence_threshold,
                decision="generate" if sufficient else "insufficient_evidence",
                chunk_count=len(chunks),
                latency_seconds=elapsed,
            )

        return RetrievalResult(
            query=query,
            chunks=chunks,
            evidence_score=score,
            attempts=1,
            sufficient=sufficient,
            applied_filter=applied_filter,
            latency_seconds=elapsed,
            collection=self.collection,
            missing=missing,
            queries_tried=[query],
        )

    # ------------------------------------------------------------------ internals

    def _search(
        self,
        query: str,
        identity: Identity,
        top_k: int | None,
    ) -> tuple[list[RetrievedChunk], dict[str, Any]]:
        """Embed, build the access filter, and run one pre-filtered search.

        The only path to the vector store in this module. Both the fixed mode and every attempt
        of the adaptive loop go through here, so neither can search without a filter.
        """
        settings = get_settings()
        applied_filter = build_access_filter(identity)
        chunks = search(
            collection=self.collection,
            query_vector=embed_query(query),
            qdrant_filter=applied_filter,
            top_k=top_k or settings.retrieval_top_k,
            identity=identity,
            score_floor=settings.retrieval_score_floor,
        )
        return chunks, applied_filter


def documents_engine() -> RetrievalEngine:
    """Engine bound to the general document corpus (the Ask surface)."""
    return RetrievalEngine(get_settings().qdrant_documents_collection)


def policy_engine() -> RetrievalEngine:
    """Engine bound to the policy corpus (the Check surface, ADR-007).

    Same class, same filter, same enforcement -- contract review is not a second, weaker path.
    """
    return RetrievalEngine(get_settings().qdrant_policy_collection)
