"""Operator settings: read-only env snapshot + runtime-writable DB overrides."""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
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
        SINGLE_LLM_MODE,
        VLLM_API_KEY,
        LLM_MODEL_ID,
    )
except ImportError:
    from config import (
        BRAVE_API_KEY,
        DEEPSEEK_API_KEY,
        DEFAULT_MODEL_PROFILE,
        LLM_MODEL_ID,
        MEMORY_POSTGRES_DSN,
        MODEL_PROFILES,
        NCBI_API_KEY,
        OPENROUTER_API_KEY,
        QUALITY_FIRST_HARD_MODE,
        AGENT_RUN_TIMEOUT_SEC,
        SINGLE_LLM_MODE,
        VLLM_API_KEY,
    )

PROFILE_LABELS: dict[str, str] = {
    "production": "Production (OpenAI)",
    "test": "Test (DeepSeek)",
    "openrouter": "OpenRouter",
    "vllm": "vLLM (Gemma)",
}

_PROVIDER_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "vllm": "LLM_API_KEY",
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
    if provider == "vllm":
        return bool(VLLM_API_KEY) and (
            _env_configured("LLM_BASE_URL") or _env_configured("VLLM_BASE_URL")
        )
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
    vllm_label = f"Gemma ({LLM_MODEL_ID})" if SINGLE_LLM_MODE else PROFILE_LABELS.get("vllm", "vllm")

    profiles: list[dict[str, Any]] = []
    for profile_id, spec in MODEL_PROFILES.items():
        ready, missing = _profile_readiness(profile_id, spec)
        profiles.append(
            {
                "id": profile_id,
                "label": vllm_label if SINGLE_LLM_MODE and profile_id == "vllm" else PROFILE_LABELS.get(profile_id, profile_id),
                "simpleModel": spec.get("simple") or "",
                "agenticModel": spec.get("agentic") or "",
                "overflowModel": spec.get("overflow"),
                "ready": ready,
                "missingEnvVars": missing,
            }
        )
    if SINGLE_LLM_MODE:
        profiles = [p for p in profiles if p["id"] == "vllm"]

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
            "id": "vllm",
            "label": "Self-hosted LLM",
            "envVar": "LLM_API_KEY",
            "configured": bool(VLLM_API_KEY)
            and (_env_configured("LLM_BASE_URL") or _env_configured("VLLM_BASE_URL")),
            "optional": not SINGLE_LLM_MODE,
            "description": "OpenAI-compatible endpoint (LLM_BASE_URL, LLM_MODEL, LLM_API_KEY).",
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

    override = get_model_profile_override()
    return {
        "defaultModelProfile": override if override else DEFAULT_MODEL_PROFILE,
        "modelProfileOverride": override,
        "envDefaultModelProfile": DEFAULT_MODEL_PROFILE,
        "singleLlmMode": SINGLE_LLM_MODE,
        "singleLlmModel": LLM_MODEL_ID if SINGLE_LLM_MODE else None,
        "modelProfiles": profiles,
        "integrations": integrations,
        "runtime": {
            "apiKeyGateEnabled": _env_configured("GENEGUIDELINES_API_KEY"),
            "agentRunTimeoutSec": AGENT_RUN_TIMEOUT_SEC,
            "mcpEnabled": not mcp_disabled,
            "qualityFirstHardMode": QUALITY_FIRST_HARD_MODE,
        },
    }


# ---------------------------------------------------------------------------
# Runtime-writable model profile override (stored in operator_kv table).
# ---------------------------------------------------------------------------

_KV_MODEL_PROFILE_KEY = "default_model_profile"
_KV_CACHE_TTL_SEC = 60

_kv_cache: dict[str, tuple[str | None, float]] = {}
_kv_cache_lock = threading.Lock()
_kv_log = logging.getLogger(__name__)


def _db_get_kv(key: str) -> str | None:
    try:
        from .database import get_connection
    except ImportError:
        from database import get_connection
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT value FROM operator_kv WHERE key = %s", (key,))
        row = cur.fetchone()
        conn.close()
        return str(row["value"]) if row else None
    except Exception as exc:
        _kv_log.debug("operator_kv read failed for key=%r: %s", key, exc)
        return None


def _db_set_kv(key: str, value: str, updated_by_clerk_id: str) -> None:
    try:
        from .database import get_connection
    except ImportError:
        from database import get_connection
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO operator_kv (key, value, updated_by_clerk_id, updated_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value,
                updated_by_clerk_id = EXCLUDED.updated_by_clerk_id,
                updated_at = EXCLUDED.updated_at
        """,
        (key, value, updated_by_clerk_id, now),
    )
    conn.commit()
    conn.close()


def _db_delete_kv(key: str) -> None:
    try:
        from .database import get_connection
    except ImportError:
        from database import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM operator_kv WHERE key = %s", (key,))
    conn.commit()
    conn.close()


def _invalidate_kv_cache(key: str) -> None:
    with _kv_cache_lock:
        _kv_cache.pop(key, None)


def get_model_profile_override() -> str | None:
    """Return the DB-stored model profile override, or None if unset (use env default)."""
    key = _KV_MODEL_PROFILE_KEY
    now = time.time()
    with _kv_cache_lock:
        entry = _kv_cache.get(key)
        if entry is not None:
            value, expires_at = entry
            if now < expires_at:
                return value
    value = _db_get_kv(key)
    with _kv_cache_lock:
        _kv_cache[key] = (value, now + _KV_CACHE_TTL_SEC)
    return value


def get_effective_default_model_profile() -> str:
    """Effective default profile: DB override if set, otherwise env-backed constant."""
    override = get_model_profile_override()
    return override if override else DEFAULT_MODEL_PROFILE


def set_model_profile_override(profile_id: str, updated_by_clerk_id: str) -> None:
    """Persist a new model profile override and invalidate the local cache."""
    if profile_id not in MODEL_PROFILES:
        raise ValueError(f"Unknown model profile: {profile_id!r}. Valid: {sorted(MODEL_PROFILES)}")
    _db_set_kv(_KV_MODEL_PROFILE_KEY, profile_id, updated_by_clerk_id)
    _invalidate_kv_cache(_KV_MODEL_PROFILE_KEY)
    _kv_log.info(
        "operator: model profile override set to %r by clerk_id=%s",
        profile_id, updated_by_clerk_id,
    )


def clear_model_profile_override(updated_by_clerk_id: str) -> None:
    """Remove the DB override — effective profile falls back to env DEFAULT_MODEL_PROFILE."""
    _db_delete_kv(_KV_MODEL_PROFILE_KEY)
    _invalidate_kv_cache(_KV_MODEL_PROFILE_KEY)
    _kv_log.info(
        "operator: model profile override cleared by clerk_id=%s", updated_by_clerk_id
    )
