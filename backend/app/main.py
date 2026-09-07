"""FastAPI application entrypoint: app construction, middleware, router mounting, lifespan.

This module owns process wiring only. It must contain no retrieval, generation, or
access-control logic -- the engine has to stay importable and usable without the web layer.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open and close shared clients (Qdrant, PostgreSQL, Ollama) for the lifetime of the app."""
    raise NotImplementedError
    yield  # pragma: no cover - signature only


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    raise NotImplementedError


# TODO:
#  1. Implement create_app(): title/version from config, mount the api router, attach lifespan,
#     then assign `app = create_app()` at module scope for uvicorn to import.
#  2. Add CORS middleware driven by settings.cors_allowed_origins (never "*" once auth exists).
#  3. Add GET /health reporting liveness plus reachability of Qdrant, PostgreSQL, and Ollama.
#  4. Implement lifespan: build the Qdrant client, DB session factory, and LLM client once;
#     assert settings.embedding_dim matches the live collection vector size and fail startup on
#     mismatch; close everything on shutdown.
#  5. Install the request-logging middleware from observability.py as the outermost layer.
#  6. Register exception handlers mapping domain errors to responses, and make the unauthorized
#     case indistinguishable from the not-found case so status codes cannot be used to
#     enumerate restricted documents.
