"""SQLAlchemy ORM models mirroring the relational schema in docs/proposal.md section 14.

Six tables: users, documents, conversations, messages, contract_reviews, clause_verdicts.
The documents table is the source of truth for access tags; Qdrant payloads are derived from it.
"""

from datetime import datetime

from sqlalchemy.orm import DeclarativeBase, Mapped


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class User(Base):
    """A user of the system, carrying the department and role authorization keys on."""

    __tablename__ = "users"

    id: Mapped[str]
    name: Mapped[str]
    department: Mapped[str]
    role: Mapped[str]
    access_level: Mapped[str]


class Document(Base):
    """An ingested source document and its access tags."""

    __tablename__ = "documents"

    id: Mapped[str]
    title: Mapped[str]
    department: Mapped[str]
    access_level: Mapped[str]
    source_path: Mapped[str]
    page_count: Mapped[int]
    ingested_at: Mapped[datetime]


class Conversation(Base):
    """One Ask session belonging to a user."""

    __tablename__ = "conversations"

    id: Mapped[str]
    user_id: Mapped[str]
    created_at: Mapped[datetime]


class Message(Base):
    """One turn in a conversation, with the citations that backed it."""

    __tablename__ = "messages"

    id: Mapped[str]
    conversation_id: Mapped[str]
    role: Mapped[str]
    content: Mapped[str]
    citations: Mapped[dict]
    created_at: Mapped[datetime]


class ContractReview(Base):
    """One submitted contract and the status of its review."""

    __tablename__ = "contract_reviews"

    id: Mapped[str]
    user_id: Mapped[str]
    contract_name: Mapped[str]
    status: Mapped[str]
    created_at: Mapped[datetime]


class ClauseVerdict(Base):
    """One clause-level verdict within a contract review."""

    __tablename__ = "clause_verdicts"

    id: Mapped[str]
    contract_review_id: Mapped[str]
    clause_index: Mapped[int]
    clause_heading: Mapped[str]
    clause_text: Mapped[str]
    verdict: Mapped[str]
    cited_policy_doc: Mapped[str]
    cited_policy_section: Mapped[str]
    explanation: Mapped[str]


# TODO:
#  1. Add mapped_column() definitions: primary keys, foreign keys, nullability, indexes.
#  2. Decide the id strategy (UUID vs. slug for documents) and apply it consistently; document
#     ids appear in citations and in the eval datasets, so they must be stable and readable.
#  3. Make documents.department and documents.access_level NOT NULL -- ingestion must not be able
#     to create an untagged document row.
#  4. Add the unique constraint on documents.source_path so re-ingest is idempotent.
#  5. Choose the citations column type (JSONB) and define its shape once, shared with the API
#     response schema so the two cannot drift.
#  6. Add relationship() definitions for conversation -> messages and review -> verdicts.
#  7. Constrain clause_verdicts.verdict to the four allowed values at the database level.
