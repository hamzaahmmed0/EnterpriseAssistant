"""Ollama client wrapper for the local Qwen model.

The single place the LLM is called from. Temperature and model tag are config, and both appear in
the eval provenance block -- a results table produced by an unrecorded model is worthless.

There is deliberately no hosted-API fallback. When local inference is slow, that is latency to
report, not a reason to change models mid-experiment (ADR-005).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings
from app.observability import log_generation


class LLMError(Exception):
    """Raised when the model server is unreachable or returns an error."""


class LLMTimeoutError(LLMError):
    """Raised when the local model does not respond in time."""


class LLMFormatError(LLMError):
    """Raised when a structured reply cannot be parsed."""


@dataclass(frozen=True)
class LLMResponse:
    """One completion, with the token counts the cost report needs."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_seconds: float


def _chat(prompt: str, system: str | None, *, json_mode: bool, purpose: str) -> LLMResponse:
    """POST one chat completion to Ollama and record it."""
    settings = get_settings()
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body: dict[str, Any] = {
        "model": settings.llm_model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": settings.llm_temperature,
            "num_predict": settings.llm_max_tokens,
        },
    }
    if json_mode:
        body["format"] = "json"

    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(url, json=body)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(
            f"{settings.llm_model} did not respond within {settings.llm_timeout_seconds}s"
        ) from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM request failed: {exc}") from exc

    elapsed = time.perf_counter() - started
    result = LLMResponse(
        text=(payload.get("message") or {}).get("content", "").strip(),
        prompt_tokens=int(payload.get("prompt_eval_count", 0)),
        completion_tokens=int(payload.get("eval_count", 0)),
        latency_seconds=elapsed,
    )
    log_generation(
        model=settings.llm_model,
        purpose=purpose,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_seconds=result.latency_seconds,
    )
    return result


def complete(prompt: str, system: str | None = None, *, purpose: str = "answer") -> LLMResponse:
    """Send a prompt to the configured local model and return its completion.

    Raises:
        LLMTimeoutError: If generation exceeds settings.llm_timeout_seconds.
        LLMError: On any other transport or server failure.
    """
    return _chat(prompt, system, json_mode=False, purpose=purpose)


def complete_json(
    prompt: str,
    system: str | None = None,
    *,
    purpose: str = "judge",
    repair_attempts: int = 1,
) -> dict[str, Any]:
    """Send a prompt expecting a structured JSON reply.

    Args:
        prompt: The user prompt.
        system: Optional system prompt.
        purpose: Log label for this call.
        repair_attempts: Bounded re-asks when the reply will not parse. Bounded on purpose: an
            unbounded repair loop is the same bug as an unbounded retrieval loop (ADR-004).

    Raises:
        LLMFormatError: If the reply is not valid JSON after the configured repair attempts.
    """
    last_text = ""
    for attempt in range(repair_attempts + 1):
        suffix = (
            ""
            if attempt == 0
            else "\n\nYour previous reply was not valid JSON. Reply with JSON only."
        )
        response = _chat(prompt + suffix, system, json_mode=True, purpose=purpose)
        last_text = response.text
        parsed = _extract_json(response.text)
        if parsed is not None:
            return parsed

    raise LLMFormatError(
        f"model did not return parseable JSON after {repair_attempts + 1} attempts: "
        f"{last_text[:200]!r}"
    )


def _extract_json(text: str) -> dict[str, Any] | None:
    """Parse a JSON object from a completion, tolerating code fences and surrounding prose."""
    if not text:
        return None
    try:
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else None
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start, end = text.find("{"), text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else None
    if candidate is None:
        return None

    try:
        loaded = json.loads(candidate)
        return loaded if isinstance(loaded, dict) else None
    except json.JSONDecodeError:
        return None


def warm_up() -> None:
    """Issue one throwaway call so the first eval query does not carry model load time.

    Called at startup and discarded by the eval harness; see docs/EVALUATION.md on latency.
    """
    try:
        complete("Reply with the single word: ready.", purpose="warmup")
    except LLMError:  # pragma: no cover - warm-up must never block startup
        pass


def health() -> dict[str, Any]:
    """Report whether the model server is reachable and the configured model is present."""
    settings = get_settings()
    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            names = {model.get("name", "") for model in response.json().get("models", [])}
    except httpx.HTTPError as exc:
        return {"reachable": False, "error": str(exc), "model_present": False}

    present = settings.llm_model in names or any(
        name.split(":")[0] == settings.llm_model.split(":")[0] for name in names
    )
    return {"reachable": True, "model_present": present, "configured_model": settings.llm_model}
