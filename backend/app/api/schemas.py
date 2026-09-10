"""Pydantic request and response models for the REST API.

The citation and verdict shapes here are the same ones persisted to PostgreSQL and returned by
the MCP tools, so a single definition governs all three (ADR-012). The contract-review
disclaimer is a required field with no default: a response cannot be constructed without it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.contracts.reviewer import Verdict

MAX_QUESTION_CHARS = 2000


class LoginRequest(BaseModel):
    """POST /auth/login body."""

    user_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    """POST /auth/login reply."""

    token: str
    user_id: str
    name: str
    department: str
    role: str
    access_level: str


class CitationOut(BaseModel):
    """A citation as returned to clients."""

    document_id: str
    document_title: str
    page: int
    chunk_id: str


class AskRequest(BaseModel):
    """POST /ask body."""

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    conversation_id: str | None = None

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Reject whitespace-only questions before they reach the engine."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("question must not be blank")
        return cleaned


class AskResponse(BaseModel):
    """POST /ask reply, including the audit fields the eval harness reads.

    ``sufficient=false`` is a normal, successful response carrying the insufficient-evidence
    answer -- it is returned with HTTP 200, not an error status.
    """

    answer: str
    citations: list[CitationOut]
    sufficient: bool
    evidence_score: float
    attempts: int
    conversation_id: str
    latency_seconds: float


class DocumentOut(BaseModel):
    """One document visible to the caller."""

    document_id: str
    title: str
    department: str
    access_level: str
    page_count: int


class ClauseVerdictOut(BaseModel):
    """One clause verdict as returned to clients."""

    clause_index: int
    heading: str
    clause_text: str
    verdict: Verdict
    cited_policy_doc: str | None
    cited_policy_section: str | None
    explanation: str


class CheckContractResponse(BaseModel):
    """POST /check-contract reply. The disclaimer is mandatory, not decorative (ADR-010)."""

    contract_review_id: str
    contract_name: str
    clauses: list[ClauseVerdictOut]
    segmentation_path: str
    disclaimer: str = Field(min_length=1)
    latency_seconds: float


class MessageOut(BaseModel):
    """One persisted conversation turn."""

    role: str
    content: str
    citations: list[CitationOut]
    sufficient: bool | None = None
    evidence_score: float | None = None


class ConversationResponse(BaseModel):
    """GET /conversation/{id} reply."""

    conversation_id: str
    messages: list[MessageOut]


class HealthResponse(BaseModel):
    """GET /health reply."""

    status: str
    postgres: dict
    qdrant: dict
    ollama: dict
