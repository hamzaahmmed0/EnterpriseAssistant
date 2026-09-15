"""Tests for session tokens and for grounded answer assembly.

Two things are pinned here that other code depends on being stable: a token cannot be forged or
replayed after expiry, and the insufficient-evidence wording is part of the API contract.
"""

from __future__ import annotations

import dataclasses
import time

import pytest

from app.auth import (
    AuthenticationError,
    Identity,
    authenticate,
    issue_token,
    verify_token,
)
from app.generation import answer as answer_module
from app.generation.answer import (
    INSUFFICIENT_EVIDENCE_MESSAGE,
    UngroundedCitationError,
    citations_to_payload,
    extract_citations,
    generate_answer,
    insufficient_evidence_answer,
)
from app.retrieval.engine import RetrievalResult


def _retrieval(chunks, *, sufficient=True, score=0.9, attempts=1) -> RetrievalResult:
    """Build a RetrievalResult without repeating every field."""
    return RetrievalResult(
        query="how much annual leave do I accrue?",
        chunks=chunks,
        evidence_score=score,
        attempts=attempts,
        sufficient=sufficient,
        applied_filter={"must": [{"key": "department", "match": {"any": ["hr"]}}]},
        latency_seconds=0.5,
        collection="documents_collection",
    )


# --------------------------------------------------------------------------- tokens


def test_round_trip_preserves_identity(hr_identity: Identity) -> None:
    """Everything authorization keys on survives a token round trip."""
    restored = verify_token(issue_token(hr_identity))
    assert restored == hr_identity


def test_tampered_payload_is_rejected(hr_identity: Identity) -> None:
    """Editing the payload without the secret must fail the signature check.

    The attack this blocks: swapping `"lvl":"internal"` for `"lvl":"confidential"`.
    """
    token = issue_token(hr_identity)
    payload, signature = token.split(".")
    forged = payload[:-2] + ("AA" if not payload.endswith("AA") else "BB")
    with pytest.raises(AuthenticationError):
        verify_token(f"{forged}.{signature}")


@pytest.mark.parametrize("bad", ["", "not-a-token", "a.b.c", "onlyonepart"])
def test_malformed_tokens_are_rejected(bad: str) -> None:
    """Structurally invalid tokens raise rather than producing a partial Identity."""
    with pytest.raises(AuthenticationError):
        verify_token(bad)


def test_expired_token_is_rejected(hr_identity: Identity) -> None:
    """A token past its TTL is refused even though its signature is valid."""
    issued_long_ago = time.time() - (10_000 * 60)
    token = issue_token(hr_identity, now=issued_long_ago)
    with pytest.raises(AuthenticationError, match="expired"):
        verify_token(token)


def test_demo_login_succeeds_and_wrong_password_fails() -> None:
    """The demo credentials work, and a wrong password does not."""
    identity = authenticate("people_member", "demo1234")
    assert identity.department == "people"
    assert identity.access_level == "internal"

    with pytest.raises(AuthenticationError):
        authenticate("people_member", "wrong")


def test_unknown_user_and_wrong_password_report_identically() -> None:
    """The error must not let a caller enumerate valid user ids."""
    with pytest.raises(AuthenticationError) as unknown:
        authenticate("no_such_user", "demo1234")
    with pytest.raises(AuthenticationError) as wrong:
        authenticate("people_member", "nope")
    assert str(unknown.value) == str(wrong.value)


def test_identity_is_immutable(hr_identity: Identity) -> None:
    """Nothing downstream may widen a caller's scope in flight."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        hr_identity.access_level = "confidential"  # type: ignore[misc]


# --------------------------------------------------------------------------- citations


def test_citations_map_to_the_right_chunks(make_chunk) -> None:
    """Block [n] maps to the nth chunk placed in the context, in order."""
    chunks = [
        make_chunk(document_id="hr-handbook", page=1, chunk_id="a"),
        make_chunk(document_id="hr-leave-policy", page=7, chunk_id="b"),
    ]
    citations = extract_citations("Leave accrues monthly [2].", _retrieval(chunks))
    assert len(citations) == 1
    assert citations[0].document_id == "hr-leave-policy"
    assert citations[0].page == 7


def test_citation_out_of_range_raises(make_chunk) -> None:
    """A model citing a block it was never given is a groundedness failure, not a warning."""
    with pytest.raises(UngroundedCitationError):
        extract_citations("As stated [4].", _retrieval([make_chunk()]))


def test_citations_are_deduplicated_in_first_mention_order(make_chunk) -> None:
    """Repeating a block must not repeat the citation."""
    chunks = [
        make_chunk(chunk_id="a", document_id="d1"),
        make_chunk(chunk_id="b", document_id="d2"),
    ]
    citations = extract_citations("[2] and again [2] and [1].", _retrieval(chunks))
    assert [citation.document_id for citation in citations] == ["d2", "d1"]


def test_titles_fall_back_to_the_document_id(make_chunk) -> None:
    """A citation is never blank, even when the relational lookup misses."""
    citations = extract_citations("[1]", _retrieval([make_chunk(document_id="hr-leave-policy")]))
    assert citations[0].document_title == "hr-leave-policy"


def test_citation_payload_shape_is_stable(make_chunk) -> None:
    """The serialised shape is shared by the API response and messages.citations (ADR-012)."""
    citations = extract_citations("[1]", _retrieval([make_chunk()]))
    payload = citations_to_payload(citations)
    assert set(payload[0]) == {"document_id", "document_title", "page", "chunk_id"}


# --------------------------------------------------------------------------- the honest exit


def test_insufficient_evidence_wording_is_pinned(make_chunk) -> None:
    """The fallback wording is part of the API contract; changing it is a breaking change."""
    result = insufficient_evidence_answer(_retrieval([make_chunk()], sufficient=False, score=0.2))
    assert result.text == INSUFFICIENT_EVIDENCE_MESSAGE
    assert result.sufficient is False
    assert result.citations == []


def test_no_llm_call_when_retrieval_was_insufficient(monkeypatch, make_chunk) -> None:
    """Generation is skipped entirely, so no parametric answer can leak in."""

    def boom(*args: object, **kwargs: object):  # noqa: ANN202
        raise AssertionError("the LLM was called despite insufficient evidence")

    monkeypatch.setattr(answer_module, "complete", boom)
    result = generate_answer("q", _retrieval([make_chunk()], sufficient=False))
    assert result.text == INSUFFICIENT_EVIDENCE_MESSAGE


def test_empty_context_never_reaches_generation(monkeypatch) -> None:
    """Sufficient=True with no chunks is still a fallback, not an ungrounded answer."""
    monkeypatch.setattr(
        answer_module, "complete", lambda *a, **k: pytest.fail("generation ran with no context")
    )
    assert generate_answer("q", _retrieval([], sufficient=True)).sufficient is False


def test_model_sentinel_becomes_the_fallback(monkeypatch, make_chunk) -> None:
    """When the model says it cannot answer, we return our wording, not the raw sentinel."""
    monkeypatch.setattr(
        answer_module,
        "complete",
        lambda *a, **k: type("R", (), {"text": "INSUFFICIENT_EVIDENCE"})(),
    )
    result = generate_answer("q", _retrieval([make_chunk()]))
    assert result.text == INSUFFICIENT_EVIDENCE_MESSAGE
    assert result.sufficient is False


def test_uncited_answer_is_rejected(monkeypatch, make_chunk) -> None:
    """Citation is required: an answer with no citations is a failure, not a partial success."""
    monkeypatch.setattr(
        answer_module,
        "complete",
        lambda *a, **k: type("R", (), {"text": "Employees get 20 days of leave."})(),
    )
    result = generate_answer("q", _retrieval([make_chunk()]))
    assert result.sufficient is False
    assert result.citations == []


def test_cited_answer_is_returned_with_its_citations(monkeypatch, make_chunk) -> None:
    """The happy path: grounded text plus a resolvable citation."""
    monkeypatch.setattr(
        answer_module,
        "complete",
        lambda *a, **k: type("R", (), {"text": "Employees accrue 20 days per year [1]."})(),
    )
    result = generate_answer("q", _retrieval([make_chunk(document_id="hr-leave-policy", page=2)]))
    assert result.sufficient is True
    assert result.citations[0].document_id == "hr-leave-policy"
    assert result.citations[0].page == 2
