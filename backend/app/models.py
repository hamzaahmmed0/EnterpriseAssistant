"""SQLAlchemy ORM models mirroring the relational schema in docs/proposal.md section 14.

Six tables: users, documents, conversations, messages, contract_reviews, clause_verdicts.
PostgreSQL is the source of truth for document metadata; Qdrant payloads are a derived copy
(ADR-008), and ingestion writes both in one unit of work.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

#: The four allowed clause verdicts, constrained at the database level (ADR-011).
VERDICT_VALUES = ("Compliant", "Deviates", "Missing", "Needs Legal Review")

#: The ordinal access levels (ADR-006), constrained at the database level.
ACCESS_LEVEL_VALUES = ("public", "internal", "confidential")


def _uuid() -> str:
    """Generate a surrogate primary key."""
    return uuid.uuid4().hex


def _now() -> datetime:
    """Timezone-aware creation timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class User(Base):
    """A user of the system, carrying the department and role authorization keys on."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    access_level: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "access_level IN ('public', 'internal', 'confidential')",
            name="ck_users_access_level",
        ),
    )


class Document(Base):
    """An ingested source document and its access tags.

    department and access_level are NOT NULL by design: ingestion must not be able to create an
    untagged document row (ADR-001).
    """

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    department: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    access_level: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)
    collection: Mapped[str] = mapped_column(String(32), nullable=False, default="documents")
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    injection_test: Mapped[bool] = mapped_column(default=False, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        UniqueConstraint("source_path", name="uq_documents_source_path"),
        CheckConstraint(
            "access_level IN ('public', 'internal', 'confidential')",
            name="ck_documents_access_level",
        ),
    )


class Conversation(Base):
    """One Ask session belonging to a user."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    """One turn in a conversation, with the citations that backed it."""

    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    #: Shape defined once by generation.answer.citations_to_payload (ADR-012).
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_score: Mapped[float | None] = mapped_column(nullable=True)
    attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sufficient: Mapped[bool | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),)


class ContractReview(Base):
    """One submitted contract and the status of its review."""

    __tablename__ = "contract_reviews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    contract_name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    clause_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    segmentation_path: Mapped[str] = mapped_column(String(32), nullable=False, default="structural")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    verdicts: Mapped[list[ClauseVerdict]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        order_by="ClauseVerdict.clause_index",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')", name="ck_contract_reviews_status"
        ),
    )


class ClauseVerdict(Base):
    """One clause-level verdict within a contract review."""

    __tablename__ = "clause_verdicts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    contract_review_id: Mapped[str] = mapped_column(
        ForeignKey("contract_reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    clause_index: Mapped[int] = mapped_column(Integer, nullable=False)
    clause_heading: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    clause_text: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    cited_policy_doc: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cited_policy_section: Mapped[str | None] = mapped_column(String(64), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_score: Mapped[float | None] = mapped_column(nullable=True)

    review: Mapped[ContractReview] = relationship(back_populates="verdicts")

    __table_args__ = (
        CheckConstraint(
            "verdict IN ('Compliant', 'Deviates', 'Missing', 'Needs Legal Review')",
            name="ck_clause_verdicts_verdict",
        ),
    )
