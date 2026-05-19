"""Per-model completion (max_tokens) ceilings for OpenAI-compatible APIs."""
from __future__ import annotations

# Substring match on model id (after provider:). First match wins.
_MODEL_ID_COMPLETION_CEILINGS: tuple[tuple[str, int], ...] = (
    ("gpt-5.5", 128_000),
    ("gpt-5.4", 128_000),
    ("gpt-4o-mini", 16_384),
    ("gpt-4o", 16_384),
    ("gpt-4.1-mini", 32_768),
    ("gpt-4.1", 32_768),
    ("gpt-4-turbo", 16_384),
    ("deepseek", 8_192),
    ("gemma", 8_192),
)

_DEFAULT_COMPLETION_CEILING = 16_384


def _model_id_from_spec(model_spec: str) -> str:
    s = (model_spec or "").strip()
    if ":" in s:
        return s.split(":", 1)[1].strip().lower()
    return s.lower()


def completion_token_ceiling(model_spec: str) -> int:
    """Best-effort max completion tokens the provider accepts for ``model_spec``."""
    mid = _model_id_from_spec(model_spec)
    for needle, cap in _MODEL_ID_COMPLETION_CEILINGS:
        if needle in mid:
            return cap
    return _DEFAULT_COMPLETION_CEILING


def cap_completion_tokens(model_spec: str, requested: int) -> int:
    """Clamp ``requested`` to the model's completion-token ceiling."""
    req = max(1, int(requested))
    return min(req, completion_token_ceiling(model_spec))
