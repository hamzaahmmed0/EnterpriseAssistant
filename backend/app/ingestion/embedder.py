"""Embedding model wrapper.

One place decides what the vectors mean. Changing the model changes EMBEDDING_DIM, the Qdrant
collection, and every number in docs/EVALUATION.md, so the model name is config and is recorded
in every results file (ADR-005).
"""


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts.

    Args:
        texts: Chunk or query texts.

    Returns:
        One vector per input, in input order, each of length settings.embedding_dim.
    """
    raise NotImplementedError


def embed_query(text: str) -> list[float]:
    """Embed a single query.

    Kept separate from embed_texts because some models require an asymmetric query prefix;
    using the document encoder for queries silently degrades retrieval.
    """
    raise NotImplementedError


def embedding_dimension() -> int:
    """Return the vector size of the configured embedding model."""
    raise NotImplementedError


# TODO:
#  1. Resolve ADR-005 open question 1 (BGE-small vs. nomic-embed-text) before implementing.
#  2. Implement embed_texts() with batching driven by settings.embedding_batch_size.
#  3. Implement embed_query(), applying the model query prefix if the chosen model needs one
#     (BGE does), and note in the docstring which convention is in force.
#  4. Implement embedding_dimension() and assert it equals settings.embedding_dim at startup.
#  5. Cache the loaded model at module level; loading per call will dominate ingest time.
#  6. Record the resolved model name and revision in the eval provenance block.
