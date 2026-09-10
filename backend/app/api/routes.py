"""REST endpoints: /auth/login, /documents, /ask, /check-contract, /conversation/{id}.

Routes stay thin. They resolve an Identity, hand it to the engine or the reviewer, and shape the
reply. No retrieval logic, no filtering, no access decisions taken here -- those belong to
retrieval.access_filter, and duplicating them here would create a second place to get it wrong.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_identity
from app.api.schemas import (
    AskRequest,
    AskResponse,
    CheckContractResponse,
    CitationOut,
    ClauseVerdictOut,
    ConversationResponse,
    DocumentOut,
    HealthResponse,
    LoginRequest,
    LoginResponse,
    MessageOut,
)
from app.auth import AuthenticationError, Identity, authenticate, issue_token
from app.config import get_settings
from app.contracts.reviewer import (
    InvalidUploadError,
    review_contract,
    validate_upload,
)
from app.db import get_session
from app.db import health as db_health
from app.generation.answer import citations_to_payload, generate_answer
from app.generation.llm import health as llm_health
from app.models import ClauseVerdict, ContractReview, Conversation, Document, Message
from app.retrieval.access_filter import can_read, visible_access_levels, visible_departments
from app.retrieval.engine import documents_engine

router = APIRouter()


# --------------------------------------------------------------------------- health


@router.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    """Liveness plus reachability of PostgreSQL, Qdrant, and Ollama."""
    from app.retrieval.vector_store import count_points

    settings = get_settings()
    try:
        qdrant = {
            "reachable": True,
            "documents": count_points(settings.qdrant_documents_collection),
            "policy": count_points(settings.qdrant_policy_collection),
        }
    except Exception as exc:  # noqa: BLE001 - health reports, never raises
        qdrant = {"reachable": False, "error": str(exc)}

    postgres = db_health()
    ollama = llm_health()
    ok = bool(postgres.get("reachable") and qdrant.get("reachable") and ollama.get("reachable"))
    return HealthResponse(
        status="ok" if ok else "degraded", postgres=postgres, qdrant=qdrant, ollama=ollama
    )


# --------------------------------------------------------------------------- auth


@router.post("/auth/login", response_model=LoginResponse, tags=["auth"])
def login(payload: LoginRequest) -> LoginResponse:
    """Authenticate a demo user and return a session token."""
    try:
        identity = authenticate(payload.user_id, payload.password)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from exc

    return LoginResponse(
        token=issue_token(identity),
        user_id=identity.user_id,
        name=identity.name,
        department=identity.department,
        role=identity.role,
        access_level=identity.access_level,
    )


# --------------------------------------------------------------------------- documents


@router.get("/documents", response_model=list[DocumentOut], tags=["documents"])
def list_documents(
    identity: Identity = Depends(current_identity),
    session: Session = Depends(get_session),
) -> list[DocumentOut]:
    """List documents the caller is authorized to see.

    The visibility rule is derived from access_filter, the same module that builds the vector
    pre-filter, so this view and retrieval cannot diverge.
    """
    rows = session.scalars(
        select(Document)
        .where(Document.department.in_(visible_departments(identity.department)))
        .where(Document.access_level.in_(visible_access_levels(identity.access_level)))
        .order_by(Document.department, Document.title)
    ).all()

    return [
        DocumentOut(
            document_id=row.id,
            title=row.title,
            department=row.department,
            access_level=row.access_level,
            page_count=row.page_count,
        )
        for row in rows
        # Belt and braces: the query already filters, and can_read re-checks the same rule.
        if can_read(identity, row.department, row.access_level)
    ]


# --------------------------------------------------------------------------- ask


@router.post("/ask", response_model=AskResponse, tags=["ask"])
def ask(
    payload: AskRequest,
    identity: Identity = Depends(current_identity),
    session: Session = Depends(get_session),
) -> AskResponse:
    """Answer a question from permission-filtered context, with citations.

    An insufficient-evidence answer is returned with HTTP 200 and ``sufficient=false``: it is an
    answer, not an error.
    """
    conversation = _resolve_conversation(session, identity, payload.conversation_id)

    retrieval = documents_engine().retrieve(payload.question, identity)
    titles = _titles_for(session, [chunk.document_id for chunk in retrieval.chunks])
    answer = generate_answer(payload.question, retrieval, titles)
    citations = citations_to_payload(answer.citations)

    session.add(
        Message(
            conversation_id=conversation.id, role="user", content=payload.question, citations=[]
        )
    )
    session.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=answer.text,
            citations=citations,
            evidence_score=answer.evidence_score,
            attempts=answer.attempts,
            sufficient=answer.sufficient,
        )
    )

    return AskResponse(
        answer=answer.text,
        citations=[CitationOut(**citation) for citation in citations],
        sufficient=answer.sufficient,
        evidence_score=answer.evidence_score,
        attempts=answer.attempts,
        conversation_id=conversation.id,
        latency_seconds=answer.latency_seconds,
    )


def _resolve_conversation(
    session: Session, identity: Identity, conversation_id: str | None
) -> Conversation:
    """Fetch the caller's conversation or start a new one.

    A conversation belonging to someone else is reported as not found, never as forbidden, so
    ids cannot be probed.
    """
    if conversation_id:
        existing = session.get(Conversation, conversation_id)
        if existing is None or existing.user_id != identity.user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
            )
        return existing

    conversation = Conversation(user_id=identity.user_id)
    session.add(conversation)
    session.flush()
    return conversation


def _titles_for(session: Session, document_ids: list[str]) -> dict[str, str]:
    """Map document ids to titles for citation display."""
    if not document_ids:
        return {}
    rows = session.scalars(select(Document).where(Document.id.in_(set(document_ids)))).all()
    return {row.id: row.title for row in rows}


# --------------------------------------------------------------------------- contracts


@router.post("/check-contract", response_model=CheckContractResponse, tags=["contracts"])
async def check_contract(
    file: UploadFile = File(...),
    identity: Identity = Depends(current_identity),
    session: Session = Depends(get_session),
) -> CheckContractResponse:
    """Review an uploaded contract clause by clause against policy."""
    settings = get_settings()
    contents = await file.read()

    try:
        validate_upload(
            filename=file.filename or "contract",
            size_bytes=len(contents),
            mime_type=_sniff_mime(contents, file.content_type),
        )
    except InvalidUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    upload_dir = Path(settings.contract_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "contract.pdf").suffix.lower()
    stored = upload_dir / f"{uuid.uuid4().hex}{suffix}"
    stored.write_bytes(contents)

    try:
        result = review_contract(str(stored), file.filename or stored.name, identity)
    except InvalidUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    review = ContractReview(
        user_id=identity.user_id,
        contract_name=result.contract_name,
        status="completed",
        clause_count=len(result.reviews),
        segmentation_path=result.segmentation_path,
    )
    session.add(review)
    session.flush()

    clauses: list[ClauseVerdictOut] = []
    for item in result.reviews:
        session.add(
            ClauseVerdict(
                contract_review_id=review.id,
                clause_index=item.clause.clause_index,
                clause_heading=item.clause.heading,
                clause_text=item.clause.text,
                verdict=item.verdict.value,
                cited_policy_doc=item.cited_policy_doc,
                cited_policy_section=item.cited_policy_section,
                explanation=item.explanation,
                evidence_score=item.evidence_score,
            )
        )
        clauses.append(
            ClauseVerdictOut(
                clause_index=item.clause.clause_index,
                heading=item.clause.heading,
                clause_text=item.clause.text,
                verdict=item.verdict,
                cited_policy_doc=item.cited_policy_doc,
                cited_policy_section=item.cited_policy_section,
                explanation=item.explanation,
            )
        )

    return CheckContractResponse(
        contract_review_id=review.id,
        contract_name=result.contract_name,
        clauses=clauses,
        segmentation_path=result.segmentation_path,
        disclaimer=result.disclaimer,
        latency_seconds=result.latency_seconds,
    )


def _sniff_mime(contents: bytes, declared: str | None) -> str:
    """Determine the MIME type from the bytes, falling back to the client's claim.

    The client's Content-Type is a hint, not evidence: a renamed .exe would carry whatever
    header the caller chose.
    """
    if contents.startswith(b"%PDF-"):
        return "application/pdf"
    if contents.startswith(b"PK\x03\x04"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return declared or "application/octet-stream"


# --------------------------------------------------------------------------- conversations


@router.get("/conversation/{conversation_id}", response_model=ConversationResponse, tags=["ask"])
def get_conversation(
    conversation_id: str,
    identity: Identity = Depends(current_identity),
    session: Session = Depends(get_session),
) -> ConversationResponse:
    """Return a conversation transcript, if it belongs to the caller."""
    conversation = session.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != identity.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    return ConversationResponse(
        conversation_id=conversation.id,
        messages=[
            MessageOut(
                role=message.role,
                content=message.content,
                citations=[CitationOut(**citation) for citation in (message.citations or [])],
                sufficient=message.sufficient,
                evidence_score=message.evidence_score,
            )
            for message in conversation.messages
        ],
    )
