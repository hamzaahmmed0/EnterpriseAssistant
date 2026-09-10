"""Coverage tests for the authentication boundary.

A forgotten `Depends(current_identity)` is a silent leak, not a visible bug: the route works, it
just works for everyone. These tests enumerate the actual app rather than trusting review.

They also assert that the MCP tools never accept a caller-supplied department or access level,
which would be privilege escalation by design (ADR-002).
"""

from __future__ import annotations

import inspect

import pytest

from app.api.deps import UNAUTHENTICATED_PATHS, current_identity


@pytest.fixture(scope="module")
def application():  # noqa: ANN201 - FastAPI app under test
    """The real app, built the way uvicorn builds it."""
    from app.main import create_app

    return create_app()


def _iter_api_routes(application):  # noqa: ANN001, ANN202
    """Yield every APIRoute in the app, whatever shape FastAPI stores them in.

    FastAPI <= 0.115 flattens an included router's routes into ``app.routes``; 0.141 wraps them
    in an ``_IncludedRouter`` that exposes ``original_router``. Walking both keeps this test
    about access control rather than about a FastAPI version.
    """
    stack = list(application.routes)
    while stack:
        route = stack.pop()
        included = getattr(route, "original_router", None)
        if included is not None:
            stack.extend(included.routes)
            continue
        if hasattr(route, "dependant"):
            yield route


def _dependency_callables(route) -> set:  # noqa: ANN001
    """Every dependency callable attached to a route."""
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return set()
    found = set()
    stack = list(dependant.dependencies)
    while stack:
        dependency = stack.pop()
        if dependency.call is not None:
            found.add(dependency.call)
        stack.extend(dependency.dependencies)
    return found


def test_every_route_requires_an_identity(application) -> None:
    """Only the login and ops endpoints may be reached without a caller."""
    unprotected = []
    for route in _iter_api_routes(application):
        path = getattr(route, "path", "")
        if path in UNAUTHENTICATED_PATHS:
            continue
        if current_identity not in _dependency_callables(route):
            unprotected.append(path)

    assert not unprotected, (
        f"these routes have no access control: {unprotected}. "
        "Add Depends(current_identity), or add the path to UNAUTHENTICATED_PATHS deliberately."
    )


def test_the_unauthenticated_allowlist_stays_small(application) -> None:
    """The allowlist is a security decision, so growing it should be a conscious act."""
    assert UNAUTHENTICATED_PATHS == {
        "/auth/login",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }


def test_expected_endpoints_exist(application) -> None:
    """The API surface matches docs/proposal.md section 13."""
    paths = {route.path for route in _iter_api_routes(application)}
    for expected in (
        "/auth/login",
        "/documents",
        "/ask",
        "/check-contract",
        "/conversation/{conversation_id}",
    ):
        assert expected in paths, f"missing endpoint {expected}"


def test_cors_is_not_a_wildcard(application) -> None:
    """An authenticated API must not allow any origin with credentials."""
    from starlette.middleware.cors import CORSMiddleware

    for middleware in application.user_middleware:
        if middleware.cls is CORSMiddleware:
            origins = middleware.kwargs.get("allow_origins", [])
            assert "*" not in origins, "CORS allows any origin on an authenticated API"


# --------------------------------------------------------------------------- MCP parity


@pytest.mark.parametrize(
    "tool_name",
    ["search_documents", "get_document_metadata", "submit_contract_for_review"],
)
def test_mcp_tools_take_a_token_and_never_an_access_level(tool_name: str) -> None:
    """MCP is a transport, not a trust boundary (ADR-002).

    A client-supplied department or access_level would let any caller mint their own permissions.
    """
    from app.mcp import server

    tool = getattr(server, tool_name)
    parameters = inspect.signature(tool).parameters

    assert "token" in parameters, f"{tool_name} does not take a session token"
    assert parameters["token"].default is inspect.Parameter.empty

    forbidden = {"department", "access_level", "identity", "user_id"}
    leaked = forbidden.intersection(parameters)
    assert not leaked, f"{tool_name} accepts caller-supplied authorization input: {sorted(leaked)}"


def test_mcp_tools_reject_a_bad_token() -> None:
    """An unauthenticated tool call returns an error payload, never results."""
    import asyncio

    from app.mcp import server

    result = asyncio.run(server.search_documents("not-a-valid-token", "anything"))
    assert "error" in result
    assert "answer" not in result


def test_mcp_server_registers_all_three_tools() -> None:
    """build_server() must actually construct and register, not just import.

    The SDK renamed FastMCP to MCPServer in mcp 2.x; this test is what catches that class of
    breakage, because a wrong import only fails when the server is really built.
    """
    import asyncio

    from app.mcp.server import build_server

    tools = asyncio.run(build_server().list_tools())
    names = {tool.name for tool in tools}
    assert names == {
        "search_documents",
        "get_document_metadata",
        "submit_contract_for_review",
    }

    for tool in tools:
        schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", {})
        properties = set(schema.get("properties", {}))
        assert "token" in properties, f"{tool.name} exposes no token parameter"
        assert (
            not {"department", "access_level"} & properties
        ), f"{tool.name} exposes caller-supplied authorization input over the wire"
