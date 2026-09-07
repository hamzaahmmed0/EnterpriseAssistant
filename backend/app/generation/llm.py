"""Ollama client wrapper for the local Qwen model.

Single place the LLM is called from. Temperature and model tag are config, and both appear in the
eval provenance block -- a results table produced by an unrecorded model is worthless.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMResponse:
    """One completion, with the token counts the cost report needs."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_seconds: float


def complete(prompt: str, system: str | None = None) -> LLMResponse:
    """Send a prompt to the configured local model and return its completion.

    Raises:
        LLMTimeoutError: If generation exceeds settings.llm_timeout_seconds.
    """
    raise NotImplementedError


def complete_json(prompt: str, system: str | None = None) -> dict:
    """Send a prompt expecting a structured JSON reply, used for clause verdicts.

    Raises:
        LLMFormatError: If the reply is not valid JSON after the configured repair attempts.
    """
    raise NotImplementedError


class LLMTimeoutError(Exception):
    """Raised when the local model does not respond in time."""


class LLMFormatError(Exception):
    """Raised when a structured reply cannot be parsed."""


# TODO:
#  1. Implement complete() against the Ollama HTTP API; pass temperature and max_tokens from
#     config, and keep temperature low so eval runs are reproducible.
#  2. Implement complete_json() with a bounded repair retry, and make the bound explicit -- an
#     unbounded repair loop is the same bug as an unbounded retrieval loop.
#  3. Emit log_generation() from both functions.
#  4. Never fall back to a hosted API on timeout; surface the timeout and report latency honestly.
#  5. Add one warm-up call at startup so the first eval query does not carry model load time.
