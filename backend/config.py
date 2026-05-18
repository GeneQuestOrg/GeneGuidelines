"""Application settings: DB path, model profiles, CORS, etc."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Backend directory (tickets.db and seed_data.json live here by default).
BACKEND_DIR = Path(__file__).resolve().parent

# Database path. Defaults to backend/tickets.db; can be overridden via the
# DB_PATH env var (used by docker-compose so the SQLite file can live on a
# named volume outside /app).
DB_PATH = Path(os.environ.get("DB_PATH") or (BACKEND_DIR / "tickets.db"))
SEED_DATA_PATH = BACKEND_DIR / "seed_data.json"

load_dotenv(BACKEND_DIR.parent / ".env")
load_dotenv(BACKEND_DIR / ".env")


def normalize_openai_compatible_base_url(url: str) -> str:
    """Ensure base URL ends with ``/v1`` for OpenAI SDK clients."""
    u = url.strip().rstrip("/")
    return u if u.endswith("/v1") else f"{u}/v1"


def _env_first(*keys: str) -> str:
    """Return the first non-empty environment value among ``keys``."""
    for key in keys:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


# Self-hosted / custom OpenAI-compatible LLM (canonical: LLM_*; legacy alias: VLLM_*).
LLM_MODEL_ID = _env_first("LLM_MODEL", "VLLM_MODEL") or "google/gemma-4-26B-A4B-it"
_LLM_API_KEY_RAW = _env_first("LLM_API_KEY", "VLLM_API_KEY")
_LLM_BASE_RAW = _env_first("LLM_BASE_URL", "VLLM_BASE_URL")

VLLM_API_KEY = _LLM_API_KEY_RAW or None
VLLM_BASE_URL = normalize_openai_compatible_base_url(_LLM_BASE_RAW) if _LLM_BASE_RAW else None
# "bearer" (OpenAI default) or "raw" (Authorization: <key> without Bearer prefix).
_LLM_AUTH_STYLE = (_env_first("LLM_AUTH_HEADER_STYLE", "VLLM_AUTH_HEADER_STYLE") or "bearer").lower()
VLLM_AUTH_HEADER_STYLE = "raw" if _LLM_AUTH_STYLE in ("raw", "token", "plain") else "bearer"

# When set, every model profile routes to this endpoint (single provider for the whole app).
SINGLE_LLM_MODE = bool(VLLM_API_KEY and VLLM_BASE_URL)
UNIFIED_LLM_MODEL_SPEC = f"vllm:{LLM_MODEL_ID}" if SINGLE_LLM_MODE else None

# Agent model (Pydantic AI) — global default
DEFAULT_MODEL_NAME = os.environ.get("DEFAULT_LLM_MODEL", "openai:gpt-5.4-mini").strip() or "openai:gpt-5.4-mini"

# Model profiles selectable per run (?profile=production|test|openrouter|vllm):
#   - "production": OpenAI (DEFAULT_SIMPLE_LLM_MODEL / DEFAULT_AGENTIC_LLM_MODEL)
#   - "test":       DeepSeek via MODEL_PROFILE_TEST_*
#   - "openrouter": OpenRouter via MODEL_PROFILE_OPENROUTER_* (requires OPENROUTER_API_KEY)
#   - "vllm":       Self-hosted vLLM (VLLM_BASE_URL + VLLM_API_KEY + VLLM_MODEL)
# DEFAULT_MODEL_PROFILE sets the fallback when the request omits ?profile=...
_ENV_DEFAULT_SIMPLE = (os.environ.get("DEFAULT_SIMPLE_LLM_MODEL") or "").strip() or DEFAULT_MODEL_NAME
_ENV_DEFAULT_AGENTIC = (os.environ.get("DEFAULT_AGENTIC_LLM_MODEL") or "").strip() or DEFAULT_MODEL_NAME
_TEST_SIMPLE = (os.environ.get("MODEL_PROFILE_TEST_SIMPLE") or "").strip() or "deepseek:deepseek-chat"
_TEST_AGENTIC = (os.environ.get("MODEL_PROFILE_TEST_AGENTIC") or "").strip() or "deepseek:deepseek-chat"

# Optional per-profile overflow fallback: when the primary model rejects a request with a
# "context length exceeded" error, the runner retries that node ONCE with this model.
# Use a big-context model here (e.g. OpenAI gpt-4.1-mini ~1M). Empty/None disables fallback.
_PROD_OVERFLOW = (
    (os.environ.get("MODEL_PROFILE_PRODUCTION_OVERFLOW") or "").strip()
    or "openai:gpt-5.5"
)
_TEST_OVERFLOW = (
    (os.environ.get("MODEL_PROFILE_TEST_OVERFLOW") or "").strip()
    or "openai:gpt-5.4-mini"
)

# Synthesis profile: heavier frontier model for the final guideline-draft step,
# the "synthesis layer" from the writeup. Gemma 4 stays in the librarian role
# (fast structured extraction); operators opt in to gpt-5.5 by passing
# `profile=synthesis` to /api/pipeline/guideline-run when they want a polished
# clinician-reviewed draft instead of the cheaper everyday run.
_SYNTHESIS_SIMPLE = (
    (os.environ.get("MODEL_PROFILE_SYNTHESIS_SIMPLE") or "").strip()
    or "openai:gpt-5.4"
)
_SYNTHESIS_AGENTIC = (
    (os.environ.get("MODEL_PROFILE_SYNTHESIS_AGENTIC") or "").strip()
    or "openai:gpt-5.5"
)

# OpenRouter (OpenAI-compatible). Used when model_spec uses `openrouter:` prefix or profile "openrouter".
_OPENROUTER_SIMPLE = (
    (os.environ.get("MODEL_PROFILE_OPENROUTER_SIMPLE") or "").strip()
    or "openrouter:google/gemma-4-31b-it"
)
_OPENROUTER_AGENTIC = (
    (os.environ.get("MODEL_PROFILE_OPENROUTER_AGENTIC") or "").strip()
    or "openrouter:google/gemma-4-31b-it"
)
_OPENROUTER_OVERFLOW = (os.environ.get("MODEL_PROFILE_OPENROUTER_OVERFLOW") or "").strip() or None

# Ollama (OpenAI-compatible). Used when model_spec uses `ollama:` prefix or profile "ollama".
# The local-edge path documented in the writeup. Default model id matches what
# the user has pulled (`ollama pull gemma4:26b`). Override via env vars.
_OLLAMA_SIMPLE = (
    (os.environ.get("MODEL_PROFILE_OLLAMA_SIMPLE") or "").strip()
    or "ollama:gemma4:26b"
)
_OLLAMA_AGENTIC = (
    (os.environ.get("MODEL_PROFILE_OLLAMA_AGENTIC") or "").strip()
    or "ollama:gemma4:26b"
)
_VLLM_SIMPLE = (os.environ.get("MODEL_PROFILE_VLLM_SIMPLE") or "").strip() or f"vllm:{LLM_MODEL_ID}"
_VLLM_AGENTIC = (os.environ.get("MODEL_PROFILE_VLLM_AGENTIC") or "").strip() or f"vllm:{LLM_MODEL_ID}"
_VLLM_OVERFLOW = (os.environ.get("MODEL_PROFILE_VLLM_OVERFLOW") or "").strip() or None

# Keys are used as profile identifiers in the API; values map prompt_mode -> model spec.
# Special key "overflow" holds a fallback model used only when the primary model hits context limits.
MODEL_PROFILES: dict[str, dict[str, str | None]] = {
    "production": {
        "simple": _ENV_DEFAULT_SIMPLE,
        "agentic": _ENV_DEFAULT_AGENTIC,
        "overflow": _PROD_OVERFLOW,
    },
    "test": {
        "simple": _TEST_SIMPLE,
        "agentic": _TEST_AGENTIC,
        "overflow": _TEST_OVERFLOW,
    },
    "openrouter": {
        "simple": _OPENROUTER_SIMPLE,
        "agentic": _OPENROUTER_AGENTIC,
        "overflow": _OPENROUTER_OVERFLOW,
    },
    "ollama": {
        "simple": _OLLAMA_SIMPLE,
        "agentic": _OLLAMA_AGENTIC,
        "overflow": None,
    },
    "vllm": {
        "simple": _VLLM_SIMPLE,
        "agentic": _VLLM_AGENTIC,
        "overflow": _VLLM_OVERFLOW,
    },
    "synthesis": {
        "simple": _SYNTHESIS_SIMPLE,
        "agentic": _SYNTHESIS_AGENTIC,
        "overflow": _PROD_OVERFLOW,
    },
}

if SINGLE_LLM_MODE and UNIFIED_LLM_MODEL_SPEC:
    for _profile_id in MODEL_PROFILES:
        MODEL_PROFILES[_profile_id] = {
            "simple": UNIFIED_LLM_MODEL_SPEC,
            "agentic": UNIFIED_LLM_MODEL_SPEC,
            "overflow": None,
        }

_env_model_profile = (os.environ.get("MODEL_PROFILE") or "").strip().lower()
if SINGLE_LLM_MODE:
    DEFAULT_MODEL_PROFILE = (
        _env_model_profile if _env_model_profile in MODEL_PROFILES else "vllm"
    )
elif _env_model_profile and _env_model_profile in MODEL_PROFILES:
    DEFAULT_MODEL_PROFILE = _env_model_profile
else:
    DEFAULT_MODEL_PROFILE = "production"

# Back-compat: a few modules still read these as module-level constants.
DEFAULT_SIMPLE_LLM_MODEL = MODEL_PROFILES[DEFAULT_MODEL_PROFILE]["simple"]
DEFAULT_AGENTIC_LLM_MODEL = MODEL_PROFILES[DEFAULT_MODEL_PROFILE]["agentic"]

if SINGLE_LLM_MODE and UNIFIED_LLM_MODEL_SPEC:
    DEFAULT_MODEL_NAME = UNIFIED_LLM_MODEL_SPEC

# DeepSeek (OpenAI-compatible API). Required when any model_spec uses `deepseek:` prefix.
DEEPSEEK_API_KEY = (os.environ.get("DEEPSEEK_API_KEY") or "").strip() or None
DEEPSEEK_BASE_URL = (os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").strip() or "https://api.deepseek.com"

# OpenRouter (OpenAI-compatible). Required when any model_spec uses `openrouter:` prefix.
OPENROUTER_API_KEY = (os.environ.get("OPENROUTER_API_KEY") or "").strip() or None
OPENROUTER_BASE_URL = (
    (os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").strip() or "https://openrouter.ai/api/v1"
)

# Ollama (OpenAI-compatible). Used when model_spec uses `ollama:` prefix. No API key —
# the daemon binds to localhost. Override base URL for remote Ollama installs.
OLLAMA_BASE_URL = (
    (os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434/v1").strip() or "http://localhost:11434/v1"
)

# Memory (persistent conversation context for agentic nodes)
MEMORY_POSTGRES_DSN = (os.environ.get("MEMORY_POSTGRES_DSN") or "").strip() or None
MEMORY_RECENT_N = int((os.environ.get("MEMORY_RECENT_N") or "").strip() or 20)

# CORS — allowed origins (frontend dev: Vite public on 5173, admin on 5174).
CORS_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

# Runtime timeouts/limits
AGENT_RUN_TIMEOUT_SEC = int((os.environ.get("AGENT_RUN_TIMEOUT_SEC") or "").strip() or 21600)
# pydantic_ai caps model round-trips per run (default 50). MCP tool loops (patient chart, PubMed) need more.
_AGENT_PYDANTIC_REQUEST_LIMIT_RAW = (os.environ.get("AGENT_PYDANTIC_AI_REQUEST_LIMIT") or "").strip()
AGENT_PYDANTIC_AI_REQUEST_LIMIT = (
    int(_AGENT_PYDANTIC_REQUEST_LIMIT_RAW) if _AGENT_PYDANTIC_REQUEST_LIMIT_RAW else 250
)
AGENT_PYDANTIC_AI_REQUEST_LIMIT = max(10, min(10_000, AGENT_PYDANTIC_AI_REQUEST_LIMIT))
SIMPLE_LLM_CALL_TIMEOUT_SEC = float((os.environ.get("SIMPLE_LLM_CALL_TIMEOUT_SEC") or "").strip() or 5400.0)
# Max concurrent simple LLM calls (PubMed pass1/pm-4 waves). Lower for self-hosted vLLM behind nginx.
_SIMPLE_LLM_PARALLEL_DEFAULT = "2" if SINGLE_LLM_MODE else "6"
SIMPLE_LLM_PARALLEL_CONCURRENCY = max(
    1,
    int((os.environ.get("SIMPLE_LLM_PARALLEL_CONCURRENCY") or "").strip() or _SIMPLE_LLM_PARALLEL_DEFAULT),
)
OPENAI_CLIENT_TIMEOUT_SEC = float((os.environ.get("OPENAI_CLIENT_TIMEOUT_SEC") or "").strip() or 2700.0)
QUALITY_FIRST_HARD_MODE = (os.environ.get("QUALITY_FIRST_HARD_MODE") or "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
QUALITY_FIRST_MAX_RETRY = int((os.environ.get("QUALITY_FIRST_MAX_RETRY") or "").strip() or 5)
MCP_SERVER_TIMEOUT_SEC = float((os.environ.get("MCP_SERVER_TIMEOUT_SEC") or "").strip() or 600.0)
HTTP_REQUEST_TIMEOUT_SEC = float((os.environ.get("HTTP_REQUEST_TIMEOUT_SEC") or "").strip() or 300.0)
CODE_NODE_TIMEOUT_SEC = float((os.environ.get("CODE_NODE_TIMEOUT_SEC") or "").strip() or 240.0)
CODE_NODE_MAX_INPUT_BYTES = int((os.environ.get("CODE_NODE_MAX_INPUT_BYTES") or "").strip() or 100_000_000)
CODE_NODE_MAX_RESULT_BYTES = int((os.environ.get("CODE_NODE_MAX_RESULT_BYTES") or "").strip() or 8_000_000)
# Token budgets for model responses. Per-node `flow_definitions.max_tokens` overrides these defaults.
# App-wide ceiling; per-model caps applied at call time (see agents.llm_limits).
# Frontier models with 1M-token contexts can override via env vars without touching code.
MAX_APP_LLM_MAX_TOKENS = 1_000_000
DEFAULT_SIMPLE_LLM_MAX_TOKENS = int(
    (os.environ.get("DEFAULT_SIMPLE_LLM_MAX_TOKENS") or "").strip() or 4_000
)
DEFAULT_AGENTIC_LLM_MAX_TOKENS = int(
    (os.environ.get("DEFAULT_AGENTIC_LLM_MAX_TOKENS") or "").strip() or 32_000
)
PUBMED_TOOL_HTTP_TIMEOUT_SEC = float((os.environ.get("PUBMED_TOOL_HTTP_TIMEOUT_SEC") or "").strip() or 900.0)
PUBMED_BROWSER_FALLBACK_ENABLED = (os.environ.get("PUBMED_BROWSER_FALLBACK_ENABLED") or "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
NCBI_API_KEY = (os.environ.get("NCBI_API_KEY") or "").strip() or None
AGENTIC_NODE_OUTPUT_MAX_CHARS = int((os.environ.get("AGENTIC_NODE_OUTPUT_MAX_CHARS") or "").strip() or 10_000_000)

# PubMed quality-first knobs
PUBMED_TOOL_SEARCH_PAGE_SIZE = int((os.environ.get("PUBMED_TOOL_SEARCH_PAGE_SIZE") or "").strip() or 200)
PUBMED_TOOL_MAX_ANALYZE = int((os.environ.get("PUBMED_TOOL_MAX_ANALYZE") or "").strip() or 5000)
PUBMED_TOOL_FETCH_BATCH_SIZE = int((os.environ.get("PUBMED_TOOL_FETCH_BATCH_SIZE") or "").strip() or 200)
PUBMED_TOOL_RETRY_ATTEMPTS = int((os.environ.get("PUBMED_TOOL_RETRY_ATTEMPTS") or "").strip() or 5)
# Doctor Finder df-4: ClinicalTrials.gov checks (sequential = unusable at thousands of authors).
_DOCTOR_FINDER_CT_MAX = (os.environ.get("DOCTOR_FINDER_CT_MAX_AUTHORS") or "").strip()
DOCTOR_FINDER_CT_MAX_AUTHORS = int(_DOCTOR_FINDER_CT_MAX) if _DOCTOR_FINDER_CT_MAX else 600
DOCTOR_FINDER_CT_MAX_AUTHORS = max(1, min(50_000, DOCTOR_FINDER_CT_MAX_AUTHORS))
_DOCTOR_FINDER_CT_CONC = (os.environ.get("DOCTOR_FINDER_CT_CONCURRENCY") or "").strip()
DOCTOR_FINDER_CT_CONCURRENCY = int(_DOCTOR_FINDER_CT_CONC) if _DOCTOR_FINDER_CT_CONC else 12
DOCTOR_FINDER_CT_CONCURRENCY = max(1, min(32, DOCTOR_FINDER_CT_CONCURRENCY))
_DOCTOR_FINDER_CT_PROG = (os.environ.get("DOCTOR_FINDER_CT_PROGRESS_EVERY") or "").strip()
DOCTOR_FINDER_CT_PROGRESS_EVERY = int(_DOCTOR_FINDER_CT_PROG) if _DOCTOR_FINDER_CT_PROG else 50
DOCTOR_FINDER_CT_PROGRESS_EVERY = max(1, DOCTOR_FINDER_CT_PROGRESS_EVERY)
# Doctor Finder df-1: PubMed OR noise — skip very short aliases in esearch; post-filter uses stricter rules.
_DOCTOR_FINDER_MIN_OR = (os.environ.get("DOCTOR_FINDER_MIN_ALIAS_OR_CHARS") or "").strip()
DOCTOR_FINDER_MIN_ALIAS_OR_CHARS = int(_DOCTOR_FINDER_MIN_OR) if _DOCTOR_FINDER_MIN_OR else 6
DOCTOR_FINDER_MIN_ALIAS_OR_CHARS = max(3, min(40, DOCTOR_FINDER_MIN_ALIAS_OR_CHARS))
_DOCTOR_FINDER_STRONG_SUB = (os.environ.get("DOCTOR_FINDER_STRONG_ALIAS_SUBSTRING_CHARS") or "").strip()
DOCTOR_FINDER_STRONG_ALIAS_SUBSTRING_CHARS = int(_DOCTOR_FINDER_STRONG_SUB) if _DOCTOR_FINDER_STRONG_SUB else 12
DOCTOR_FINDER_STRONG_ALIAS_SUBSTRING_CHARS = max(8, min(80, DOCTOR_FINDER_STRONG_ALIAS_SUBSTRING_CHARS))
_DOCTOR_FINDER_MED_SUB = (os.environ.get("DOCTOR_FINDER_MEDIUM_ALIAS_SUBSTRING_CHARS") or "").strip()
DOCTOR_FINDER_MEDIUM_ALIAS_SUBSTRING_CHARS = int(_DOCTOR_FINDER_MED_SUB) if _DOCTOR_FINDER_MED_SUB else 8
DOCTOR_FINDER_MEDIUM_ALIAS_SUBSTRING_CHARS = max(6, min(40, DOCTOR_FINDER_MEDIUM_ALIAS_SUBSTRING_CHARS))
# df-1 post-fetch: match disease/aliases only in title + first N abstract chars (drops passing mentions deep in reviews).
_DF_REL_LEAD = (os.environ.get("DOCTOR_FINDER_RELEVANCE_LEAD_CHARS") or "").strip()
DOCTOR_FINDER_RELEVANCE_LEAD_CHARS = int(_DF_REL_LEAD) if _DF_REL_LEAD else 700
DOCTOR_FINDER_RELEVANCE_LEAD_CHARS = max(200, min(12_000, DOCTOR_FINDER_RELEVANCE_LEAD_CHARS))

# Brave Search + LLM affiliation geolocation (Doctor Finder df-20). Optional — unset key skips the step.
BRAVE_API_KEY = (os.environ.get("BRAVE_API_KEY") or "").strip() or None
_DFG_GEO_MAX = (os.environ.get("DOCTOR_FINDER_GEO_MAX_AFFILIATIONS") or "").strip()
DOCTOR_FINDER_GEO_MAX_AFFILIATIONS = int(_DFG_GEO_MAX) if _DFG_GEO_MAX else 280
DOCTOR_FINDER_GEO_MAX_AFFILIATIONS = max(1, min(500, DOCTOR_FINDER_GEO_MAX_AFFILIATIONS))
_DFG_GEO_CONC = (os.environ.get("DOCTOR_FINDER_GEO_BRAVE_CONCURRENCY") or "").strip()
DOCTOR_FINDER_GEO_BRAVE_CONCURRENCY = int(_DFG_GEO_CONC) if _DFG_GEO_CONC else 4
DOCTOR_FINDER_GEO_BRAVE_CONCURRENCY = max(1, min(16, DOCTOR_FINDER_GEO_BRAVE_CONCURRENCY))
_DFG_GEO_CONF = (os.environ.get("DOCTOR_FINDER_GEO_CONFIDENCE_MIN") or "").strip()
DOCTOR_FINDER_GEO_CONFIDENCE_MIN = float(_DFG_GEO_CONF) if _DFG_GEO_CONF else 0.66
DOCTOR_FINDER_GEO_CONFIDENCE_MIN = max(0.35, min(0.99, DOCTOR_FINDER_GEO_CONFIDENCE_MIN))
_DFG_GEO_MINCH = (os.environ.get("DOCTOR_FINDER_GEO_MIN_AFF_CHARS") or "").strip()
DOCTOR_FINDER_GEO_MIN_AFF_CHARS = int(_DFG_GEO_MINCH) if _DFG_GEO_MINCH else 14
DOCTOR_FINDER_GEO_MIN_AFF_CHARS = max(8, min(200, DOCTOR_FINDER_GEO_MIN_AFF_CHARS))

PUBMED_RETRIEVAL_MIN_PMIDS_PER_DOMAIN = int(
    (os.environ.get("PUBMED_RETRIEVAL_MIN_PMIDS_PER_DOMAIN") or "").strip() or 50
)
PUBMED_RETRIEVAL_TARGET_PMIDS = int((os.environ.get("PUBMED_RETRIEVAL_TARGET_PMIDS") or "").strip() or 800)
# pm-1: deterministic multi-domain PubMed orchestration (default). Runs every clinical
# query variant + high-recall backfill; uses disease aliases when present. Set to 0 only
# to restore the legacy agentic pm-1 step (not recommended — skips domains, TPM failures).
PUBMED_PM1_DETERMINISTIC_RETRIEVAL = (
    (os.environ.get("PUBMED_PM1_DETERMINISTIC_RETRIEVAL") or "1").strip().lower()
    in ("1", "true", "yes", "on")
)
# OpenAI org TPM per-request budget (e.g. gpt-5.5-long-context = 400k). Caps articles_text in LLM prompts.
OPENAI_TPM_REQUEST_TOKEN_BUDGET = int(
    (os.environ.get("OPENAI_TPM_REQUEST_TOKEN_BUDGET") or "").strip() or 380_000
)
# Abstract chars per article line inside prompt ``articles_text`` (pm-2 code node may use more).
PUBMED_ARTICLES_TEXT_ABSTRACT_MAX_CHARS = int(
    (os.environ.get("PUBMED_ARTICLES_TEXT_ABSTRACT_MAX_CHARS") or "").strip() or 3000
)

# Guidelines RAG — comma-separated anchor PMIDs override (env var)
_GUIDELINES_RAG_PMIDS_RAW = (os.environ.get("GUIDELINES_RAG_ANCHOR_PMIDS") or "").strip()
GUIDELINES_RAG_ANCHOR_PMIDS: list[str] = (
    [p.strip() for p in _GUIDELINES_RAG_PMIDS_RAW.split(",") if p.strip()]
    if _GUIDELINES_RAG_PMIDS_RAW
    else []
)
