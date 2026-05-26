"""Per-model completion (max_tokens) and prompt-input ceilings for OpenAI-compatible APIs."""
from __future__ import annotations

# Reserve for system prompt, structured output, and provider overhead (not in articles_text budget).
_PROMPT_INPUT_TOKEN_RESERVE = 12_000

# Substring match on model id (after provider:). First match wins.
_MODEL_ID_INPUT_CONTEXT_CEILINGS: tuple[tuple[str, int], ...] = (
    ("gemma-4-31b", 262_144),
    ("gemma-4-31", 262_144),
    ("gemma4", 131_072),
    ("gpt-5.5", 1_000_000),
    ("gpt-5.4", 1_000_000),
    ("gpt-4.1", 1_047_576),
    ("gpt-4o", 128_000),
    ("deepseek", 128_000),
)

_DEFAULT_INPUT_CONTEXT_CEILING = 128_000

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


def input_context_token_ceiling(model_spec: str | None) -> int:
    """Best-effort total context window for ``model_spec`` (input + completion)."""
    if not model_spec:
        return _DEFAULT_INPUT_CONTEXT_CEILING
    mid = _model_id_from_spec(model_spec)
    for needle, cap in _MODEL_ID_INPUT_CONTEXT_CEILINGS:
        if needle in mid:
            return cap
    return _DEFAULT_INPUT_CONTEXT_CEILING


def prompt_input_token_budget(model_spec: str | None = None) -> int:
    """Cap PubMed prompt corpus size for the active model and OPENAI_TPM_REQUEST_TOKEN_BUDGET."""
    from ..config import OPENAI_TPM_REQUEST_TOKEN_BUDGET

    tpm_cap = OPENAI_TPM_REQUEST_TOKEN_BUDGET
    model_cap = max(8_000, input_context_token_ceiling(model_spec) - _PROMPT_INPUT_TOKEN_RESERVE)
    return min(tpm_cap, model_cap)
