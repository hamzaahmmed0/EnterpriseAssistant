"""Evidence scoring: does the retrieved context actually support an answer?

ADR-004 resolves this as an LLM-as-judge call rather than a similarity heuristic, because the
failure mode that matters is a chunk that is topically close but does not contain the fact asked
for -- which similarity scores rate highly by construction.

The score drives the adaptive loop and is logged for every attempt, so its definition is part of
the experimental method, not an implementation detail. Two consequences are handled here:

* The judge costs an LLM round-trip per attempt. That is measured, not hidden.
* The judge is not deterministic. Mitigated by temperature 0, strict JSON output, and a cache
  keyed on (question, chunk ids, prompt version) so re-running the same config over the frozen
  set replays the same verdicts. Residual non-determinism is a stated limitation.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.generation import prompts
from app.generation.llm import LLMError, complete_json
from app.retrieval.vector_store import RetrievedChunk


@dataclass(frozen=True)
class EvidenceJudgement:
    """The judge's verdict on one retrieval attempt."""

    score: float
    sufficient: bool
    missing: str


_cache_lock = threading.Lock()
_cache: dict[str, dict] | None = None


def _cache_key(question: str, chunks: list[RetrievedChunk]) -> str:
    """Stable key for a (question, evidence set) pair under the current judge prompt."""
    material = json.dumps(
        {
            "q": question.strip(),
            "chunks": sorted(chunk.chunk_id for chunk in chunks),
            "prompt": prompts.JUDGE_PROMPT_VERSION,
            "model": get_settings().llm_model,
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, dict]:
    """Read the judge cache from disk once per process."""
    global _cache
    if _cache is None:
        path = Path(get_settings().judge_cache_path)
        try:
            _cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            _cache = {}
    return _cache


def _store_cache(key: str, value: dict) -> None:
    """Persist one judgement. Best-effort: a cache write failure must not fail a request."""
    cache = _load_cache()
    with _cache_lock:
        cache[key] = value
        path = Path(get_settings().judge_cache_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(cache, indent=0), encoding="utf-8")
        except OSError:  # pragma: no cover - cache is an optimisation, never a dependency
            pass


def clear_cache() -> None:
    """Drop the in-memory judge cache. Tests only."""
    global _cache
    with _cache_lock:
        _cache = None


def judge_evidence(question: str, chunks: list[RetrievedChunk]) -> EvidenceJudgement:
    """Ask the model whether these chunks are sufficient to answer the question.

    Args:
        question: The query used for this retrieval attempt.
        chunks: Chunks returned by the filtered search, highest scoring first.

    Returns:
        The judgement, including what the judge says is missing -- used to seed the query
        reformulation on the next attempt.
    """
    if not chunks:
        # Defined for the empty case: zero, not an error, and no LLM call to pay for.
        return EvidenceJudgement(score=0.0, sufficient=False, missing="no documents were retrieved")

    key = _cache_key(question, chunks)
    cached = _load_cache().get(key)
    if cached is not None:
        return EvidenceJudgement(
            score=float(cached["score"]),
            sufficient=bool(cached["sufficient"]),
            missing=str(cached.get("missing", "")),
        )

    try:
        reply = complete_json(
            prompts.judge_prompt(question, [chunk.text for chunk in chunks]),
            prompts.judge_system_prompt(),
            purpose="judge",
        )
    except LLMError:
        # A judge failure must not silently green-light generation. Fail closed: treat the
        # evidence as insufficient and let the loop retry or fall back honestly.
        return EvidenceJudgement(score=0.0, sufficient=False, missing="evidence judge unavailable")

    score = _coerce_score(reply.get("score"))
    judgement = EvidenceJudgement(
        score=score,
        sufficient=bool(reply.get("sufficient", score >= get_settings().evidence_threshold)),
        missing=str(reply.get("missing", "") or ""),
    )
    _store_cache(
        key,
        {
            "score": judgement.score,
            "sufficient": judgement.sufficient,
            "missing": judgement.missing,
        },
    )
    return judgement


def _coerce_score(raw: object) -> float:
    """Clamp whatever the model returned into [0, 1], defaulting to 0 on nonsense."""
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    if value != value:  # NaN
        return 0.0
    return max(0.0, min(1.0, value))


def score_evidence(question: str, chunks: list[RetrievedChunk]) -> float:
    """Score how well the retrieved chunks support answering the question.

    Returns:
        A score in [0, 1], comparable across queries and configurations.
    """
    return judge_evidence(question, chunks).score


def is_sufficient(score: float, threshold: float) -> bool:
    """Whether the evidence clears the configured threshold.

    The only place a score is compared to the threshold. Keeping it in one function means a
    sweep of EVIDENCE_THRESHOLD cannot miss a second, hardcoded comparison somewhere else.
    """
    return score >= threshold
