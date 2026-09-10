"""The regression guard for the whole class of access-control bug.

These tests do not check that the filter is *correct* -- test_access_filter.py does that. They
check that it is impossible to reach the vector store without one, which is the property that
survives refactoring, new retrieval modes, and a second transport.
"""

from __future__ import annotations

import inspect

import pytest

from app.retrieval import vector_store
from app.retrieval.access_filter import AccessFilterError


def test_search_requires_a_filter_and_an_identity() -> None:
    """Neither the filter nor the caller may be optional or defaulted."""
    parameters = inspect.signature(vector_store.search).parameters
    for required in ("qdrant_filter", "identity"):
        assert required in parameters, f"search() lost its {required} parameter"
        assert (
            parameters[required].default is inspect.Parameter.empty
        ), f"search() gave {required} a default; it must be impossible to omit"


def test_module_exposes_exactly_one_search_entry_point() -> None:
    """A second search function is how an unfiltered path gets added by accident."""
    search_functions = [
        name
        for name, value in vars(vector_store).items()
        if callable(value)
        and not name.startswith("_")
        and "search" in name.lower()
        and getattr(value, "__module__", "") == vector_store.__name__
    ]
    assert search_functions == ["search"], f"unexpected search entry points: {search_functions}"


def test_search_rejects_an_empty_filter(hr_identity, monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty filter is refused before any client call is made.

    The fake client records calls; the assertion is that it recorded none, i.e. the guard fired
    before the query was ever issued rather than after results came back.
    """
    calls: list[dict] = []

    class NeverCalledClient:
        def search(self, **kwargs: object) -> list:
            calls.append(kwargs)
            return []

    monkeypatch.setattr(vector_store, "get_client", lambda: NeverCalledClient())

    for empty in ({}, {"must": []}):
        with pytest.raises(AccessFilterError):
            vector_store.search(
                collection="documents_collection",
                query_vector=[0.0] * 8,
                qdrant_filter=empty,
                top_k=5,
                identity=hr_identity,
            )

    assert calls == [], "an unfiltered search reached the client before the guard fired"


def test_upsert_refuses_untagged_chunks() -> None:
    """An untagged chunk is a hole in the access boundary, so ingest fails rather than warns."""
    incomplete = {
        "chunk_id": "doc::0000::abc",
        "vector": [0.0] * 8,
        "payload": {"document_id": "doc", "page": 1, "chunk_index": 0},  # no tags
    }
    with pytest.raises(vector_store.VectorStoreError) as excinfo:
        vector_store.upsert_chunks("documents_collection", [incomplete])

    message = str(excinfo.value)
    assert "department" in message and "access_level" in message


def test_upsert_of_nothing_is_a_no_op() -> None:
    """An empty batch must not touch the client at all."""
    assert vector_store.upsert_chunks("documents_collection", []) == 0


def test_engine_search_always_passes_a_filter(hr_identity, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every engine path reaches the store with a populated filter.

    Exercised through the engine rather than the store, because the engine is where a new
    retrieval mode would be added -- and where the filter would be forgotten.
    """
    from app.retrieval import engine as engine_module

    captured: list[dict] = []

    def fake_search(
        *, collection, query_vector, qdrant_filter, top_k, identity, score_floor=None
    ):  # noqa: ANN001, ANN202
        captured.append(qdrant_filter)
        return []

    monkeypatch.setattr(engine_module, "search", fake_search)
    monkeypatch.setattr(engine_module, "embed_query", lambda text: [0.0] * 8)

    engine_module.RetrievalEngine("documents_collection").retrieve_fixed(
        "how much annual leave do I get?", hr_identity, judge=False
    )

    assert captured, "engine did not reach the vector store at all"
    for applied in captured:
        assert applied, "engine reached the vector store with an empty filter"
        keys = {condition["key"] for condition in applied["must"]}
        assert keys == {"department", "access_level"}
