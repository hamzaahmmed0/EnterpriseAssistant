"""Embedding model wrapper (ADR-005: nomic-embed-text served by Ollama).

One place decides what the vectors mean. Changing the model changes EMBEDDING_DIM, the Qdrant
collection, and every number in docs/EVALUATION.md, so the model name is config and is recorded
in every results file.

nomic-embed-text is asymmetric: documents and queries take different task prefixes. Using the
document prefix for a query silently degrades retrieval without raising anything, which is why
embed_texts and embed_query are separate functions rather than one with a flag.
"""

from __future__ import annotations

import httpx

from app.config import get_settings

DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


class EmbeddingError(Exception):
    """Raised when the embedding service fails or returns an unusable response."""


def _post_embed(inputs: list[str]) -> list[list[float]]:
    """Embed a batch through the configured provider (ollama or openai)."""
    if get_settings().embedding_provider == "openai":
        return _post_embed_openai(inputs)
    return _post_embed_ollama(inputs)


def _post_embed_openai(inputs: list[str]) -> list[list[float]]:
    """Call OpenAI's embeddings endpoint. Returns vectors in input order."""
    settings = get_settings()
    url = f"{settings.openai_base_url.rstrip('/')}/embeddings"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(
                url,
                headers=headers,
                json={"model": settings.openai_embedding_model, "input": inputs},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise EmbeddingError(f"OpenAI embedding request failed: {exc}") from exc

    data = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
    vectors = [item.get("embedding") for item in data]
    if not vectors or len(vectors) != len(inputs) or any(v is None for v in vectors):
        raise EmbeddingError(
            f"OpenAI returned {len(vectors)} vectors for {len(inputs)} inputs"
        )
    return [[float(value) for value in vector] for vector in vectors]


def _post_embed_ollama(inputs: list[str]) -> list[list[float]]:
    """Call Ollama's embedding endpoint, tolerating both API shapes it has shipped."""
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/embed"
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(url, json={"model": settings.embedding_model, "input": inputs})
            if response.status_code == 404:
                # Older Ollama: one prompt per request against /api/embeddings.
                return [_post_embed_legacy(client, text) for text in inputs]
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise EmbeddingError(f"embedding request failed: {exc}") from exc

    vectors = payload.get("embeddings")
    if vectors is None and "embedding" in payload:
        vectors = [payload["embedding"]]
    if not vectors or len(vectors) != len(inputs):
        raise EmbeddingError(
            f"embedding service returned {len(vectors or [])} vectors for {len(inputs)} inputs"
        )
    return [[float(value) for value in vector] for vector in vectors]


def _post_embed_legacy(client: httpx.Client, text: str) -> list[float]:
    """Single-input fallback for Ollama versions without /api/embed."""
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/embeddings"
    response = client.post(url, json={"model": settings.embedding_model, "prompt": text})
    response.raise_for_status()
    vector = response.json().get("embedding")
    if not vector:
        raise EmbeddingError("embedding service returned an empty vector")
    return [float(value) for value in vector]


def _check_dimension(vectors: list[list[float]]) -> list[list[float]]:
    """Fail loudly on a dimension mismatch; a silent one corrupts every retrieval result."""
    expected = get_settings().embedding_dim
    for vector in vectors:
        if len(vector) != expected:
            raise EmbeddingError(
                f"embedding dimension mismatch: model returned {len(vector)}, "
                f"EMBEDDING_DIM is {expected}. Fix .env or re-create the collection."
            )
    return vectors


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of document chunks.

    Args:
        texts: Chunk texts. Each is sent with the document task prefix.

    Returns:
        One vector per input, in input order, each of length settings.embedding_dim.
    """
    if not texts:
        return []

    settings = get_settings()
    prefix = "" if settings.embedding_provider == "openai" else DOCUMENT_PREFIX
    batch_size = max(1, settings.embedding_batch_size)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = [prefix + text for text in texts[start : start + batch_size]]
        vectors.extend(_post_embed(batch))
    return _check_dimension(vectors)


def embed_query(text: str) -> list[float]:
    """Embed a single query, with the query task prefix.

    Kept separate from embed_texts because nomic-embed-text is asymmetric; using the document
    encoder for queries degrades retrieval silently.
    """
    if not text or not text.strip():
        raise EmbeddingError("refusing to embed an empty query")
    prefix = "" if get_settings().embedding_provider == "openai" else QUERY_PREFIX
    return _check_dimension(_post_embed([prefix + text]))[0]


def embedding_dimension() -> int:
    """Return the vector size the configured model actually produces.

    Used at startup to assert the live Qdrant collection agrees with EMBEDDING_DIM.
    """
    prefix = "" if get_settings().embedding_provider == "openai" else QUERY_PREFIX
    probe = _post_embed([prefix + "dimension probe"])
    return len(probe[0])
