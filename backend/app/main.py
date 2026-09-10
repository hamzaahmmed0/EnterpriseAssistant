"""FastAPI application entrypoint: app construction, middleware, router mounting, lifespan.

This module owns process wiring only. It contains no retrieval, generation, or access-control
logic -- the engine stays importable and usable without the web layer.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import get_settings
from app.observability import configure_logging, current_query_id, log_error, new_query_id
from app.retrieval.access_filter import AccessFilterError
from app.retrieval.vector_store import VectorStoreError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open and close shared clients (Qdrant, PostgreSQL, Ollama) for the lifetime of the app."""
    from app.db import init_schema, reset_engine_cache
    from app.generation.llm import warm_up
    from app.ingestion.embedder import EmbeddingError, embedding_dimension
    from app.retrieval.vector_store import ensure_collection, reset_client_cache

    settings = get_settings()
    configure_logging(settings.log_level)

    init_schema()

    # A dimension mismatch corrupts every retrieval result silently, so it fails startup loudly.
    try:
        live_dimension = embedding_dimension()
    except EmbeddingError as exc:
        raise RuntimeError(f"cannot reach the embedding model: {exc}") from exc
    if live_dimension != settings.embedding_dim:
        raise RuntimeError(
            f"{settings.embedding_model} produces {live_dimension}-dimension vectors but "
            f"EMBEDDING_DIM is {settings.embedding_dim}. Fix .env or re-create the collections."
        )

    for collection in (settings.qdrant_documents_collection, settings.qdrant_policy_collection):
        ensure_collection(collection, settings.embedding_dim)

    warm_up()

    try:
        yield
    finally:
        reset_client_cache()
        reset_engine_cache()


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    application = FastAPI(
        title="Enterprise Knowledge Assistant",
        version="0.1.0",
        description=(
            "Access-controlled document Q&A and contract compliance review. Access control is "
            "enforced as a pre-filter inside vector search, identically over REST and MCP."
        ),
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,  # never "*": the API is authenticated
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @application.middleware("http")
    async def correlate_and_log(request: Request, call_next):  # noqa: ANN001, ANN202
        """Mint a query id for the request and record its outcome."""
        new_query_id()
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001 - logged, then re-raised to the handlers below
            log_error(
                "request_failed",
                path=request.url.path,
                method=request.method,
                error=str(exc),
                latency_seconds=round(time.perf_counter() - started, 3),
            )
            raise
        response.headers["X-Query-Id"] = current_query_id()
        return response

    @application.exception_handler(AccessFilterError)
    async def _access_filter_error(request: Request, exc: AccessFilterError) -> JSONResponse:
        """An unconstrainable identity is a server-side failure, never a permissive fallback."""
        log_error("access_filter_error", path=request.url.path, error=str(exc))
        return JSONResponse(status_code=500, content={"detail": "Request could not be authorized"})

    @application.exception_handler(VectorStoreError)
    async def _vector_store_error(request: Request, exc: VectorStoreError) -> JSONResponse:
        """Index misconfiguration is an operator problem; do not leak internals to the caller."""
        log_error("vector_store_error", path=request.url.path, error=str(exc))
        return JSONResponse(status_code=503, content={"detail": "Search backend unavailable"})

    @application.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError) -> JSONResponse:
        """Domain validation failures become 400s with the message, not a stack trace."""
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    application.include_router(router)
    return application


app = create_app()
