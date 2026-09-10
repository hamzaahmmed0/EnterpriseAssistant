"""Single source of truth for every tunable in the system.

Thresholds, chunk sizes, top-k, retry caps, and model names live here and nowhere else --
calibration means sweeping these, which is impossible if they are inlined at call sites.
Every field maps 1:1 to a variable in `.env.example`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RetrievalMode = Literal["fixed", "hybrid_rerank", "adaptive"]


class Settings(BaseSettings):
    """Application configuration, loaded from environment / .env.

    Fields that encode a decision from docs/DECISIONS.md carry that decision's default. Fields
    that are secrets carry none, so a missing one fails loudly at startup.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------------------------------------------------------------- app
    app_env: str = "local"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_allowed_origins: str = "http://localhost:3000"

    # ---------------------------------------------------------------- auth (ADR-006)
    auth_secret: str
    auth_token_ttl_minutes: int = 480
    demo_users_path: str = "backend/demo_users.json"

    # ---------------------------------------------------------------- postgres (ADR-008)
    database_url: str = "postgresql+psycopg://eka:eka@localhost:5432/eka"

    # ---------------------------------------------------------------- qdrant (ADR-007)
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str | None = None
    qdrant_documents_collection: str = "documents_collection"
    qdrant_policy_collection: str = "policy_collection"

    # ---------------------------------------------------------------- embeddings (ADR-005)
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768
    embedding_batch_size: int = 16

    # ---------------------------------------------------------------- llm (ADR-005)
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 1024
    llm_timeout_seconds: int = 180

    # ---------------------------------------------------------------- ingestion (ADR-003)
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64
    ingest_source_dir: str = "data/corpus"
    ingest_manifest_path: str = "data/corpus/manifest.json"

    # ---------------------------------------------------------------- retrieval (ADR-004, ADR-012)
    retrieval_top_k: int = 5
    eval_report_k: int = 5
    retrieval_score_floor: float | None = None
    evidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    adaptive_max_attempts: int = 3
    retrieval_mode: RetrievalMode = "adaptive"
    reranker_model: str | None = None
    judge_cache_path: str = "eval/results/.judge_cache.json"

    # ---------------------------------------------------------------- contracts (ADR-009, ADR-011)
    contract_max_upload_mb: int = 10
    contract_allowed_mime_types: str = (
        "application/pdf," "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    contract_top_k: int = 5
    contract_upload_dir: str = "data/contracts"
    segmentation_max_clause_chars: int = 4000

    # ---------------------------------------------------------------- mcp (ADR-002)
    mcp_transport: Literal["stdio", "http"] = "stdio"
    mcp_http_port: int | None = 8001

    # ---------------------------------------------------------------- derived accessors
    @property
    def cors_origins(self) -> list[str]:
        """CORS origins as a list. Never "*" -- the API is authenticated."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def allowed_mime_types(self) -> set[str]:
        """Upload MIME allowlist as a set."""
        return {m.strip() for m in self.contract_allowed_mime_types.split(",") if m.strip()}

    @property
    def contract_max_upload_bytes(self) -> int:
        """Upload size limit in bytes."""
        return self.contract_max_upload_mb * 1024 * 1024

    @property
    def qdrant_url(self) -> str:
        """Base URL of the Qdrant HTTP API."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    # ---------------------------------------------------------------- validation
    @model_validator(mode="after")
    def _check_invariants(self) -> Settings:
        """Reject configurations that would silently produce meaningless results."""
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError(
                "chunk_overlap_tokens must be smaller than chunk_size_tokens "
                f"(got {self.chunk_overlap_tokens} >= {self.chunk_size_tokens})"
            )
        if not 2 <= self.adaptive_max_attempts <= 3:
            raise ValueError(
                "adaptive_max_attempts must be 2 or 3 (ADR-004 hard cap), "
                f"got {self.adaptive_max_attempts}"
            )
        if self.retrieval_mode == "hybrid_rerank" and not self.reranker_model:
            raise ValueError("retrieval_mode=hybrid_rerank requires RERANKER_MODEL to be set")
        if self.retrieval_top_k < 1:
            raise ValueError("retrieval_top_k must be >= 1")
        if self.embedding_dim < 1:
            raise ValueError("embedding_dim must be >= 1")
        return self

    # ---------------------------------------------------------------- provenance
    def provenance(self) -> dict[str, object]:
        """The config block every eval results file must embed.

        Results without provenance are discarded (docs/EVALUATION.md), so this defines what
        "the config that produced this number" means. Secrets are deliberately excluded:
        auth_secret, database_url, and qdrant_api_key never appear here.
        """
        return {
            "retrieval_mode": self.retrieval_mode,
            "llm_model": self.llm_model,
            "llm_temperature": self.llm_temperature,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "chunk_size_tokens": self.chunk_size_tokens,
            "chunk_overlap_tokens": self.chunk_overlap_tokens,
            "retrieval_top_k": self.retrieval_top_k,
            "eval_report_k": self.eval_report_k,
            "retrieval_score_floor": self.retrieval_score_floor,
            "evidence_threshold": self.evidence_threshold,
            "adaptive_max_attempts": self.adaptive_max_attempts,
            "reranker_model": self.reranker_model,
            "contract_top_k": self.contract_top_k,
            "segmentation_max_clause_chars": self.segmentation_max_clause_chars,
        }


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()  # type: ignore[call-arg]  # values come from env / .env


def reset_settings_cache() -> None:
    """Clear the settings cache. Tests only -- production config is immutable per process."""
    get_settings.cache_clear()
