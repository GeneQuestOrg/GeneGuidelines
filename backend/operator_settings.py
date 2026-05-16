"""Read-only operator settings snapshot (env-backed; never exposes secret values)."""
from __future__ import annotations

import os
from typing import Any

try:
    from .config import (
        BRAVE_API_KEY,
        DEEPSEEK_API_KEY,
        DEFAULT_MODEL_PROFILE,
        MEMORY_POSTGRES_DSN,
        MODEL_PROFILES,
        NCBI_API_KEY,
        OPENROUTER_API_KEY,
        QUALITY_FIRST_HARD_MODE,
        AGENT_RUN_TIMEOUT_SEC,
    )
except ImportError:
    from config import (
        BRAVE_API_KEY,
        DEEPSEEK_API_KEY,
        DEFAULT_MODEL_PROFILE,
        MEMORY_POSTGRES_DSN,
        MODEL_PROFILES,
        NCBI_API_KEY,
        OPENROUTER_API_KEY,
        QUALITY_FIRST_HARD_MODE,
        AGENT_RUN_TIMEOUT_SEC,
    )

PROFILE_LABELS: dict[str, str] = {
    "production": "Production (OpenAI)",
    "test": "Test (DeepSeek)",
    "openrouter": "OpenRouter",
}

_PROVIDER_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _env_configured(name: str) -> bool:
    return bool((os.environ.get(name) or "").strip())


def _model_provider(model_spec: str | None) -> str | None:
    if not model_spec or not isinstance(model_spec, str):
        return None
    trimmed = model_spec.strip()
    if ":" not in trimmed:
        return None
    return trimmed.split(":", 1)[0].lower()


def _provider_configured(provider: str) -> bool:
    if provider == "openai":
        return _env_configured("OPENAI_API_KEY")
    if provider == "deepseek":
        return bool(DEEPSEEK_API_KEY)
    if provider == "openrouter":
        return bool(OPENROUTER_API_KEY)
    return False


def _profile_readiness(profile_id: str, spec: dict[str, str | None]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for key in ("simple", "agentic", "overflow"):
        model = spec.get(key)
        if not model:
            continue
        provider = _model_provider(model)
        if provider is None:
            continue
        env_name = _PROVIDER_ENV.get(provider)
        if env_name and not _provider_configured(provider):
            if env_name not in missing:
                missing.append(env_name)
    return (len(missing) == 0, missing)


def get_operator_settings() -> dict[str, Any]:
    """Build settings payload for admin UI (camelCase keys)."""
    profiles: list[dict[str, Any]] = []
    for profile_id, spec in MODEL_PROFILES.items():
        ready, missing = _profile_readiness(profile_id, spec)
        profiles.append(
            {
                "id": profile_id,
                "label": PROFILE_LABELS.get(profile_id, profile_id),
                "simpleModel": spec.get("simple") or "",
                "agenticModel": spec.get("agentic") or "",
                "overflowModel": spec.get("overflow"),
                "ready": ready,
                "missingEnvVars": missing,
            }
        )

    integrations: list[dict[str, Any]] = [
        {
            "id": "api_gate",
            "label": "GeneGuidelines API key gate",
            "envVar": "GENEGUIDELINES_API_KEY",
            "configured": _env_configured("GENEGUIDELINES_API_KEY"),
            "optional": True,
            "description": "When set, protected API routes require Bearer or X-API-Key.",
        },
        {
            "id": "openai",
            "label": "OpenAI",
            "envVar": "OPENAI_API_KEY",
            "configured": _env_configured("OPENAI_API_KEY"),
            "optional": False,
            "description": "Required for production profile and OpenAI-prefixed models.",
        },
        {
            "id": "deepseek",
            "label": "DeepSeek",
            "envVar": "DEEPSEEK_API_KEY",
            "configured": bool(DEEPSEEK_API_KEY),
            "optional": True,
            "description": "Required when using deepseek: model specs (test profile).",
        },
        {
            "id": "openrouter",
            "label": "OpenRouter",
            "envVar": "OPENROUTER_API_KEY",
            "configured": bool(OPENROUTER_API_KEY),
            "optional": True,
            "description": "Required for openrouter: model specs.",
        },
        {
            "id": "brave",
            "label": "Brave Search",
            "envVar": "BRAVE_API_KEY",
            "configured": bool(BRAVE_API_KEY),
            "optional": True,
            "description": "Doctor Finder geo enrichment (df-20).",
        },
        {
            "id": "ncbi",
            "label": "NCBI / PubMed",
            "envVar": "NCBI_API_KEY",
            "configured": bool(NCBI_API_KEY),
            "optional": True,
            "description": "Raises PubMed rate limits; optional but recommended at scale.",
        },
        {
            "id": "memory",
            "label": "Postgres memory",
            "envVar": "MEMORY_POSTGRES_DSN",
            "configured": bool(MEMORY_POSTGRES_DSN),
            "optional": True,
            "description": "Persistent agent memory across runs.",
        },
    ]

    mcp_disabled = os.environ.get("AGENT_NO_MCP_RUNTIME", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    return {
        "defaultModelProfile": DEFAULT_MODEL_PROFILE,
        "modelProfiles": profiles,
        "integrations": integrations,
        "runtime": {
            "apiKeyGateEnabled": _env_configured("GENEGUIDELINES_API_KEY"),
            "agentRunTimeoutSec": AGENT_RUN_TIMEOUT_SEC,
            "mcpEnabled": not mcp_disabled,
            "qualityFirstHardMode": QUALITY_FIRST_HARD_MODE,
        },
    }
