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


def resolve_gemma_or_fallback_spec() -> str:
    """Return a primary model spec the agent layer can call.

    Preference order:

    1. ``openrouter`` profile if ``OPENROUTER_API_KEY`` is set — that is the
       documented Gemma 4 demo path on managed infrastructure.
    2. The operator's ``DEFAULT_MODEL_PROFILE`` if its provider has its key.
    3. Any other profile in ``MODEL_PROFILES`` whose provider has its key
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
        "ollama": "local" if _ollama_reachable() else None,
    }
    candidates = ["openrouter", DEFAULT_MODEL_PROFILE, "production", "test", "ollama"]
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
    timeout_sec: float,
) -> tuple[BaseModel, str]:
    """Run a structured-output agent; on HTTP 429 from the primary, retry on Ollama.

    Returns ``(parsed_output, model_spec_actually_used)`` so the caller can log
    which model produced the result.

    Only HTTP 429 (rate-limit) triggers the fallback. Other failures bubble up
    so callers can record them in ``guideline_run_results``.
    """
    from ..agents import agent as agent_module

    async def _call(spec: str):
        ag = agent_module.get_simple_structured_agent(
            system_prompt, result_type, model_spec=spec, max_tokens=max_tokens
        )
        return await asyncio.wait_for(ag.run(user_prompt), timeout=timeout_sec)

    try:
        res = await _call(primary_spec)
        return _coerce_output(res, result_type), primary_spec
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
        return _coerce_output(res, result_type), fallback_spec


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
    "run_structured_with_ollama_fallback",
]
