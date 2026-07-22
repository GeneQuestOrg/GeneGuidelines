"""Pick the right model spec for a service-layer Gemma call, with local fallback.

Workflows in this project advertise themselves as Gemma-powered. When
``OPENROUTER_API_KEY`` is set we route through OpenRouter's Gemma 4 endpoint —
that is the documented demo path. When a local Ollama daemon is running with
a ``gemma4`` model pulled, we use it as a fallback for the (paid-tier) 429s
that OpenRouter occasionally returns when the upstream provider rate-limits.
The writeup is honest about this: the same prompts run unchanged against a
local Ollama Gemma instance for clinics that need the bytes to stay on-prem.
"""

from __future__ import annotations

import asyncio
import logging
import os
import urllib.parse
import urllib.request
from typing import Type

from pydantic import BaseModel

log = logging.getLogger(__name__)

_finder_llm_parallel_semaphore: asyncio.Semaphore | None = None


def _get_finder_llm_parallel_semaphore() -> asyncio.Semaphore:
    """Process-wide cap on concurrent finder LLM calls (bootstrap fan-out)."""
    global _finder_llm_parallel_semaphore
    if _finder_llm_parallel_semaphore is None:
        from ..config import FINDER_LLM_PARALLEL_CONCURRENCY

        _finder_llm_parallel_semaphore = asyncio.Semaphore(FINDER_LLM_PARALLEL_CONCURRENCY)
    return _finder_llm_parallel_semaphore


def reset_finder_llm_parallel_semaphore_for_tests() -> None:
    """Allow tests to pick up a fresh semaphore after env overrides."""
    global _finder_llm_parallel_semaphore
    _finder_llm_parallel_semaphore = None


def resolve_gemma_or_fallback_spec() -> str:
    """Return a primary model spec the agent layer can call.

    Preference order:

    1. The operator's ``DEFAULT_MODEL_PROFILE`` if its provider has its key.
    2. Any other profile in ``MODEL_PROFILES`` whose provider has its key
       (production, test). Ollama is checked last because it is treated as
       the local-edge fallback, not the primary spec for the demo.

    Raises :class:`RuntimeError` if no profile has a usable key and Ollama
    is unreachable.
    """
    from ..config import (
        DEFAULT_MODEL_PROFILE,
        DEEPSEEK_API_KEY,
        MODEL_PROFILES,
        OPENROUTER_API_KEY,
    )

    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip() or None
    key_for_profile = {
        "openrouter": OPENROUTER_API_KEY,
        "production": openai_key,
        "test": DEEPSEEK_API_KEY,
        "vllm": (os.environ.get("LLM_API_KEY") or os.environ.get("VLLM_API_KEY") or "").strip() or None,
        "ollama": "local" if _ollama_reachable() else None,
    }
    candidates = [
        DEFAULT_MODEL_PROFILE,
        "production",
        "vllm",
        "openrouter",
        "test",
        "ollama",
    ]
    seen: set[str] = set()
    for name in candidates:
        if name in seen or name not in MODEL_PROFILES:
            continue
        seen.add(name)
        if key_for_profile.get(name):
            profile = MODEL_PROFILES[name]
            spec = profile.get("simple") or profile.get("agentic")
            if spec:
                return spec
    raise RuntimeError(
        "No model profile has its API key set and Ollama is unreachable. "
        "Configure one of OPENROUTER_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY "
        "or run `ollama serve` with a Gemma model pulled."
    )


def resolve_local_fallback_spec() -> str | None:
    """Return a local-edge model spec (Ollama Gemma) if available, else None."""
    if not _ollama_reachable():
        return None
    from ..config import MODEL_PROFILES

    profile = MODEL_PROFILES.get("ollama") or {}
    return profile.get("simple") or profile.get("agentic")


def _ollama_reachable() -> bool:
    """Quick check whether the Ollama daemon is up. 200ms timeout to keep it cheap."""
    from ..config import OLLAMA_BASE_URL

    try:
        # /v1 base URL → strip the trailing /v1 for /api/tags probe
        base = OLLAMA_BASE_URL.rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        url = base + "/api/tags"
        urllib.request.urlopen(url, timeout=0.6)
        return True
    except Exception:
        return False


async def run_structured_with_ollama_fallback(
    *,
    system_prompt: str,
    user_prompt: str,
    result_type: Type[BaseModel],
    primary_spec: str,
    max_tokens: int,
    timeout_sec: float | None = None,
    return_usage: bool = False,
):
    """Run a structured-output agent; on HTTP 429 from the primary, retry on Ollama.

    Returns ``(parsed_output, model_spec_actually_used)`` so the caller can log
    which model produced the result.

    When ``return_usage=True`` a third element is appended — a best-effort
    ``(prompt_tokens, completion_tokens, total_tokens)`` triple extracted from
    the agent run — so a caller can append a ``token_usage`` ledger row per call
    (the content-translation worker does this). The default ``False`` keeps the
    original two-tuple contract for every existing caller
    (e.g. :mod:`backend.services.disease_wider_search`).

    Only HTTP 429 (rate-limit) triggers the fallback. Other failures bubble up
    so callers can record them in ``guideline_run_results``.

    Finder calls share ``FINDER_LLM_PARALLEL_CONCURRENCY`` so bootstrap fan-out
    does not stampede the upstream LLM endpoint.
    """
    from ..agents import agent as agent_module
    from ..config import FINDER_LLM_TIMEOUT_SEC

    effective_timeout = (
        float(timeout_sec) if timeout_sec is not None else FINDER_LLM_TIMEOUT_SEC
    )

    async def _call(spec: str):
        ag = agent_module.get_simple_structured_agent(
            system_prompt, result_type, model_spec=spec, max_tokens=max_tokens
        )
        async with _get_finder_llm_parallel_semaphore():
            return await asyncio.wait_for(ag.run(user_prompt), timeout=effective_timeout)

    def _result(res, spec: str):
        out = _coerce_output(res, result_type)
        if return_usage:
            return out, spec, _extract_usage(res)
        return out, spec

    try:
        res = await _call(primary_spec)
        return _result(res, primary_spec)
    except Exception as exc:  # noqa: BLE001 — we narrow the 429 case below
        if not _is_429_error(exc):
            raise
        fallback_spec = resolve_local_fallback_spec()
        if not fallback_spec:
            raise
        log.warning(
            "primary spec %s returned 429; falling back to local Ollama (%s)",
            primary_spec,
            fallback_spec,
        )
        res = await _call(fallback_spec)
        return _result(res, fallback_spec)


def _extract_usage(res) -> tuple[int, int, int]:
    """Best-effort ``(prompt, completion, total)`` for a run (0s if unavailable)."""
    try:
        from ..research_queue.token_budget import extract_usage

        return extract_usage(res)
    except Exception:  # noqa: BLE001 — usage extraction must never break a call
        return (0, 0, 0)


def _coerce_output(res, result_type: Type[BaseModel]) -> BaseModel:
    out = getattr(res, "output", None) or getattr(res, "data", None)
    if isinstance(out, result_type):
        return out
    if isinstance(out, dict):
        return result_type.model_validate(out)
    raise RuntimeError(f"Unexpected agent output type: {type(out).__name__}")


def _is_429_error(exc: BaseException) -> bool:
    """True when the exception (or its cause) is a 429 from the model provider."""
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and getattr(cause, "status_code", None) == 429:
        return True
    # pydantic_ai wraps the OpenAI client error message; cheap text probe.
    if "429" in str(exc):
        return True
    return False


__all__ = [
    "resolve_gemma_or_fallback_spec",
    "resolve_local_fallback_spec",
    "reset_finder_llm_parallel_semaphore_for_tests",
    "run_structured_with_ollama_fallback",
]
