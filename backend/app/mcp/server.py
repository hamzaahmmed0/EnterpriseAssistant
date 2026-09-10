"""MCP server exposing the retrieval and contract-review tools.

MCP is a transport, not a trust boundary (ADR-002). Every tool takes the caller's session token,
resolves it through the same ``auth.verify_token`` the HTTP dependency uses, and goes through the
same access-control path. There is no internal mode, no service identity, and no bypass flag --
the red-team suite runs through here as well as through HTTP, and both results are reported.

Note what these signatures deliberately do *not* accept: ``department`` and ``access_level``. A
client-supplied access level is privilege escalation by design.

Run::

    python -m app.mcp.server
"""

from __future__ import annotations

import base64
import binascii
import tempfile
from pathlib import Path
from typing import Any

from app.auth import AuthenticationError, Identity, verify_token
from app.config import get_settings
from app.contracts.reviewer import InvalidUploadError, review_contract, validate_upload
from app.db import session_scope
from app.generation.answer import citations_to_payload, generate_answer
from app.observability import configure_logging, new_query_id
from app.retrieval.access_filter import visible_access_levels, visible_departments
from app.retrieval.engine import documents_engine

TOOL_ERROR = "error"


def _identity_or_error(token: str) -> tuple[Identity | None, dict[str, Any] | None]:
    """Resolve a token into an Identity, or return the error payload to hand back to the client."""
    try:
        return verify_token(token), None
    except AuthenticationError:
        return None, {TOOL_ERROR: "Not authenticated. Obtain a token from POST /auth/login."}


async def search_documents(token: str, query: str, top_k: int | None = None) -> dict[str, Any]:
    """Search the document corpus as the caller identified by the token.

    Args:
        token: Session token issued by /auth/login.
        query: Natural-language query.
        top_k: Optional override for settings.retrieval_top_k.

    Returns:
        Answer text, citations, and the evidence-score/attempt fields, matching AskResponse.
        An insufficient-evidence result is a normal return with ``sufficient: false``.
    """
    new_query_id()
    identity, error = _identity_or_error(token)
    if error:
        return error
    assert identity is not None

    if not query or not query.strip():
        return {TOOL_ERROR: "query must not be empty"}

    retrieval = documents_engine().retrieve(query, identity, top_k)

    with session_scope() as session:
        from sqlalchemy import select

        from app.models import Document

        ids = {chunk.document_id for chunk in retrieval.chunks}
        titles = (
            {
                row.id: row.title
                for row in session.scalars(select(Document).where(Document.id.in_(ids))).all()
            }
            if ids
            else {}
        )

    answer = generate_answer(query, retrieval, titles)
    return {
        "answer": answer.text,
        "citations": citations_to_payload(answer.citations),
        "sufficient": answer.sufficient,
        "evidence_score": answer.evidence_score,
        "attempts": answer.attempts,
    }


async def get_document_metadata(token: str, document_id: str | None = None) -> dict[str, Any]:
    """Return metadata for documents the caller may see.

    A caller must not learn that a restricted document exists, so an unauthorized ``document_id``
    is reported identically to a nonexistent one.
    """
    new_query_id()
    identity, error = _identity_or_error(token)
    if error:
        return error
    assert identity is not None

    from sqlalchemy import select

    from app.models import Document

    with session_scope() as session:
        statement = (
            select(Document)
            .where(Document.department.in_(visible_departments(identity.department)))
            .where(Document.access_level.in_(visible_access_levels(identity.access_level)))
        )
        if document_id:
            statement = statement.where(Document.id == document_id)
        rows = session.scalars(statement.order_by(Document.department, Document.title)).all()

        documents = [
            {
                "document_id": row.id,
                "title": row.title,
                "department": row.department,
                "access_level": row.access_level,
                "page_count": row.page_count,
            }
            for row in rows
        ]

    if document_id and not documents:
        return {TOOL_ERROR: "Document not found"}
    return {"documents": documents}


async def submit_contract_for_review(
    token: str,
    contract_name: str,
    contract_base64: str,
) -> dict[str, Any]:
    """Review a contract clause by clause as the caller.

    The result carries the decision-support disclaimer, exactly as the HTTP response does
    (ADR-010).
    """
    new_query_id()
    identity, error = _identity_or_error(token)
    if error:
        return error
    assert identity is not None

    try:
        contents = base64.b64decode(contract_base64, validate=True)
    except (binascii.Error, ValueError):
        return {TOOL_ERROR: "contract_base64 is not valid base64"}

    suffix = Path(contract_name).suffix.lower() or ".pdf"
    mime = (
        "application/pdf"
        if contents.startswith(b"%PDF-")
        else (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if contents.startswith(b"PK\x03\x04")
            else "application/octet-stream"
        )
    )

    try:
        validate_upload(filename=contract_name, size_bytes=len(contents), mime_type=mime)
    except InvalidUploadError as exc:
        return {TOOL_ERROR: str(exc)}

    upload_dir = Path(get_settings().contract_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=upload_dir, suffix=suffix, delete=False) as handle:
        handle.write(contents)
        stored = handle.name

    try:
        result = review_contract(stored, contract_name, identity)
    except InvalidUploadError as exc:
        return {TOOL_ERROR: str(exc)}

    return {
        "contract_name": result.contract_name,
        "segmentation_path": result.segmentation_path,
        "clauses": [
            {
                "clause_index": item.clause.clause_index,
                "heading": item.clause.heading,
                "clause_text": item.clause.text,
                "verdict": item.verdict.value,
                "cited_policy_doc": item.cited_policy_doc,
                "cited_policy_section": item.cited_policy_section,
                "explanation": item.explanation,
            }
            for item in result.reviews
        ],
        # Required, and asserted by a test: no human sees this payload during development.
        "disclaimer": result.disclaimer,
    }


def build_server() -> Any:
    """Construct the MCP server and register the three tools.

    The SDK renamed ``FastMCP`` to ``MCPServer`` in mcp 2.x; both names are tried so the server
    runs on either major version rather than failing at import with a confusing error.
    """
    try:
        from mcp.server.mcpserver import MCPServer as ServerClass  # mcp >= 2
    except ImportError:  # pragma: no cover - depends on the installed SDK
        from mcp.server.fastmcp import FastMCP as ServerClass  # mcp < 2

    server = ServerClass(
        name="enterprise-knowledge-assistant",
        instructions=(
            "Tools for an access-controlled internal knowledge base. Every tool requires a "
            "session token from POST /auth/login; results are restricted to what that user may "
            "read. Contract review is decision support, not legal advice."
        ),
    )
    server.tool(
        name="search_documents",
        description=(
            "Search internal company documents and return a cited answer. Requires a session "
            "token; results are restricted to what that user is authorized to read."
        ),
    )(search_documents)
    server.tool(
        name="get_document_metadata",
        description="List metadata for the internal documents the token holder may access.",
    )(get_document_metadata)
    server.tool(
        name="submit_contract_for_review",
        description=(
            "Review a base64-encoded PDF/DOCX contract clause by clause against internal policy. "
            "Returns decision support, not legal advice."
        ),
    )(submit_contract_for_review)
    return server


def main() -> None:
    """CLI entrypoint: run the MCP server over the configured transport."""
    settings = get_settings()
    configure_logging(settings.log_level)
    server = build_server()

    if settings.mcp_transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport="streamable-http", port=settings.mcp_http_port or 8001)


if __name__ == "__main__":  # pragma: no cover
    main()
