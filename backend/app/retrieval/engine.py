"""The retrieval engine: the one entry point every consumer uses.

Ask, Check, and the MCP server all call this. It takes an Identity and a query, applies the
access filter, runs the configured retrieval mode, and returns scored evidence. It does not
generate answers, and it does not know what a web request is.
"""

from dataclasses import dataclass

from app.auth import Identity
from app.retrieval.vector_store import RetrievedChunk


@dataclass(frozen=True)
class RetrievalResult:
    """The outcome of one retrieval, carrying everything the eval harness needs to score it."""

    query: str
    chunks: list[RetrievedChunk]
    evidence_score: float
    attempts: int
    sufficient: bool
    applied_filter: dict
    latency_seconds: float


class RetrievalEngine:
    """Permission-aware retrieval over a Qdrant collection."""

    def __init__(self, collection: str) -> None:
        """Bind the engine to a collection (documents or policy)."""
        raise NotImplementedError

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
        """
        raise NotImplementedError

    def retrieve_fixed(self, query: str, identity: Identity, top_k: int) -> RetrievalResult:
        """Single-shot filtered retrieval with no retry. Config A, the baseline."""
        raise NotImplementedError


# TODO:
#  1. Implement __init__: hold the collection name, embedder, and settings; no client per call.
#  2. Implement retrieve_fixed(): embed query, build filter, search, score, return. This is the
#     Sprint 1 baseline and the reference every other mode is compared against.
#  3. Implement retrieve() dispatch over settings.retrieval_mode; adaptive delegates to
#     adaptive.run_adaptive_retrieval, keeping the loop logic out of this class.
#  4. Populate applied_filter on every RetrievalResult so results files can prove which filter ran.
#  5. Make top_k for generation and the k=5 used for metric reporting explicitly separate values
#     (open question in docs/DECISIONS.md); do not conflate them.
#  6. Add the Config B hybrid + reranker path only after Sprint 2 lands -- it is the first cut.
#  7. Integration test: two identities, same query, different result sets, neither containing a
#     chunk the caller may not read.
