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
    """Send one chat completion through the configured provider and record it."""
    settings = get_settings()
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    started = time.perf_counter()
    if settings.llm_provider == "openai":
        result = _chat_openai(messages, json_mode=json_mode, started=started)
    else:
        result = _chat_ollama(messages, json_mode=json_mode, started=started)

    log_generation(
        model=settings.active_llm_model,
        purpose=purpose,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        latency_seconds=result.latency_seconds,
    )
    return result


def _chat_ollama(messages: list[dict[str, str]], *, json_mode: bool, started: float) -> LLMResponse:
    """POST one chat completion to Ollama."""
    settings = get_settings()
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

    return LLMResponse(
        text=(payload.get("message") or {}).get("content", "").strip(),
        prompt_tokens=int(payload.get("prompt_eval_count", 0)),
        completion_tokens=int(payload.get("eval_count", 0)),
        latency_seconds=time.perf_counter() - started,
    )


def _chat_openai(messages: list[dict[str, str]], *, json_mode: bool, started: float) -> LLMResponse:
    """POST one chat completion to the OpenAI-compatible /chat/completions endpoint."""
    settings = get_settings()
    body: dict[str, Any] = {
        "model": settings.openai_llm_model,
        "messages": messages,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    try:
        with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(
            f"{settings.openai_llm_model} did not respond within {settings.llm_timeout_seconds}s"
        ) from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"OpenAI request failed: {exc}") from exc

    choices = payload.get("choices") or [{}]
    usage = payload.get("usage") or {}
    return LLMResponse(
        text=(choices[0].get("message") or {}).get("content", "").strip(),
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
        latency_seconds=time.perf_counter() - started,
    )


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
    if settings.llm_provider == "openai":
        try:
            with httpx.Client(timeout=8) as client:
                response = client.get(
                    f"{settings.openai_base_url.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                )
                response.raise_for_status()
                names = {m.get("id", "") for m in response.json().get("data", [])}
        except httpx.HTTPError as exc:
            return {"reachable": False, "error": str(exc), "model_present": False}
        return {
            "reachable": True,
            "model_present": settings.openai_llm_model in names,
            "configured_model": settings.openai_llm_model,
        }
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
