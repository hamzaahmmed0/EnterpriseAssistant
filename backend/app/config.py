"""Single source of truth for every tunable in the system.

Thresholds, chunk sizes, top-k, retry caps, and model names live here and nowhere else --
calibration means sweeping these, which is impossible if they are inlined at call sites.
Every field maps 1:1 to a variable in `.env.example`.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings

RetrievalMode = Literal["fixed", "hybrid_rerank", "adaptive"]


class Settings(BaseSettings):
    """Application configuration, loaded from environment / .env.

    No field carries a default that could silently stand in for an undecided open question
    (chunk size, evidence threshold, embedding model). Those must fail loudly if unset.
    """

    # app
    app_env: str
    log_level: str
    api_host: str
    api_port: int
    cors_allowed_origins: str

    # auth (demo)
    auth_secret: str
    auth_token_ttl_minutes: int
    demo_users_path: str

    # postgres
    database_url: str

    # qdrant
    qdrant_host: str
    qdrant_port: int
    qdrant_api_key: str | None
    qdrant_documents_collection: str
    qdrant_policy_collection: str

    # embeddings
    embedding_model: str
    embedding_dim: int
    embedding_batch_size: int

    # llm
    ollama_base_url: str
    llm_model: str
    llm_temperature: float
    llm_max_tokens: int
    llm_timeout_seconds: int

    # ingestion
    chunk_size_tokens: int
    chunk_overlap_tokens: int
    ingest_source_dir: str

    # retrieval
    retrieval_top_k: int
    retrieval_score_floor: float | None
    evidence_threshold: float
    adaptive_max_attempts: int
    retrieval_mode: RetrievalMode
    reranker_model: str | None

    # contracts
    contract_max_upload_mb: int
    contract_allowed_mime_types: str
    contract_top_k: int

    # mcp
    mcp_transport: Literal["stdio", "http"]
    mcp_http_port: int | None

    def provenance(self) -> dict[str, object]:
        """Return the config block that every eval results file must embed.

        Results without provenance are discarded (docs/EVALUATION.md), so this function
        defines what "the config that produced this number" means.
        """
        raise NotImplementedError


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    raise NotImplementedError


# TODO:
#  1. Implement get_settings(): load Settings, cache it, let validation errors propagate.
#  2. Add a validator rejecting chunk_overlap_tokens >= chunk_size_tokens.
#  3. Add a validator rejecting adaptive_max_attempts outside 2..3 (ADR-004 hard cap).
#  4. Add a validator requiring reranker_model when retrieval_mode == "hybrid_rerank".
#  5. Implement provenance(): emit exactly the fields listed in docs/EVALUATION.md 1.4, and
#     nothing secret -- never auth_secret, database_url, or qdrant_api_key.
#  6. Add the startup assertion (called from main.py) that embedding_dim matches the live
#     Qdrant collection vector size; a mismatch corrupts every retrieval result silently.
