"""MCP server exposing the retrieval and contract-review tools.

MCP is a transport, not a trust boundary. Every tool takes the caller identity and goes through
the same access-control path as an HTTP request. There is no internal mode, no service identity,
and no bypass flag -- the red-team suite runs through here as well as through HTTP, and both
results are reported.
"""

from typing import Any


async def search_documents(token: str, query: str, top_k: int | None = None) -> dict[str, Any]:
    """Search the document corpus as the caller identified by the token.

    Args:
        token: Session token issued by /auth/login. Resolved through auth.verify_token, the same
            function the HTTP dependency uses.
        query: Natural-language query.
        top_k: Optional override for settings.retrieval_top_k.

    Returns:
        Answer text, citations, and the evidence-score/attempt fields, matching AskResponse.
    """
    raise NotImplementedError


async def get_document_metadata(token: str, document_id: str | None = None) -> dict[str, Any]:
    """Return metadata for documents the caller may see.

    A caller must not be able to learn that a restricted document exists, so an unauthorized
    document_id is indistinguishable from a nonexistent one.
    """
    raise NotImplementedError


async def submit_contract_for_review(
    token: str,
    contract_name: str,
    contract_base64: str,
) -> dict[str, Any]:
    """Review a contract clause by clause as the caller.

    The result carries the decision-support disclaimer, exactly as the HTTP response does.
    """
    raise NotImplementedError


def build_server() -> Any:
    """Construct the MCP server and register the three tools."""
    raise NotImplementedError


def main() -> None:
    """CLI entrypoint: run the MCP server over the configured transport."""
    raise NotImplementedError


# TODO:
#  1. Implement the three tools as thin wrappers over the exact functions the HTTP routes call;
#     if a tool needs its own retrieval code, the seam is wrong.
#  2. Resolve identity via auth.verify_token only. Never accept a department or access_level as a
#     tool argument -- a client-supplied access level is privilege escalation by design.
#  3. Implement build_server() with tool schemas and descriptions; register all three tools.
#  4. Implement main() honouring settings.mcp_transport (stdio first; http only if ADR-002 note
#     is resolved that way).
#  5. Run the full red-team suite through these tools and record the MCP column in
#     docs/EVALUATION.md section 5. Sprint 2 needs search_documents only; the other two land in
#     Sprint 3 and get re-tested then.
#  6. Test that submit_contract_for_review includes the disclaimer in its result payload.
#  7. Document the client config snippet for README setup step 9.
