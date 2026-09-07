"""Pydantic request and response models for the REST API.

The citation and verdict shapes defined here are shared with the persistence layer and the MCP
tool results, so a single definition governs all three.
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """POST /auth/login body."""

    user_id: str
    password: str


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

    question: str
    conversation_id: str | None = None


class AskResponse(BaseModel):
    """POST /ask reply, including the audit fields the eval harness reads."""

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
    verdict: str
    cited_policy_doc: str | None
    cited_policy_section: str | None
    explanation: str


class CheckContractResponse(BaseModel):
    """POST /check-contract reply. The disclaimer field is mandatory, not decorative."""

    contract_review_id: str
    contract_name: str
    clauses: list[ClauseVerdictOut]
    disclaimer: str
    latency_seconds: float


class ConversationResponse(BaseModel):
    """GET /conversation/{id} reply."""

    conversation_id: str
    messages: list[dict]


# TODO:
#  1. Add field validators: non-empty question, question length cap, conversation_id ownership
#     checked at the route (a caller must not read another user conversation).
#  2. Constrain ClauseVerdictOut.verdict to the Verdict enum rather than a bare string.
#  3. Make disclaimer non-optional with no default, so a response cannot be built without it.
#  4. Derive CitationOut from the same definition used by messages.citations in models.py.
#  5. Add example payloads for the OpenAPI docs once the shapes are settled.
