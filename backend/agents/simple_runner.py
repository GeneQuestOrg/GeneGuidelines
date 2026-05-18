"""
LLM Call (Simple): one model call, no MCP, structured output (Pydantic), retry up to max_retry.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from queue import Queue
from typing import Any, Type

from pydantic import BaseModel

from . import agent as agent_module
from ..config import SIMPLE_LLM_CALL_TIMEOUT_SEC

# Active model profile for the current async context (set per request by the router).
# Falls back to DEFAULT_MODEL_PROFILE from config when unset.
current_model_profile: ContextVar[str | None] = ContextVar("current_model_profile", default=None)


def resolve_active_profile() -> str:
    """Return the model profile name active for this request, or the configured default."""
    from ..config import DEFAULT_MODEL_PROFILE, MODEL_PROFILES

    name = (current_model_profile.get() or "").strip().lower() or DEFAULT_MODEL_PROFILE
    if name not in MODEL_PROFILES:
        name = DEFAULT_MODEL_PROFILE
    return name


def resolve_model_spec_for_node(node: dict) -> str:
    """Pick the model spec for a node given the active profile.

    Hierarchy: explicit node.model_name (override) → profile[prompt_mode] → profile["agentic"].
    """
    from ..config import MODEL_PROFILES

    raw = (node.get("model_name") or "").strip()
    if raw:
        return raw if ":" in raw else f"openai:{raw}"

    profile = resolve_active_profile()
    profile_models = MODEL_PROFILES[profile]
    mode = (node.get("prompt_mode") or "agentic").strip().lower()
    spec = profile_models.get(mode) or profile_models.get("agentic")
    assert spec, f"Profile '{profile}' missing required model for mode '{mode}'"
    return spec


def resolve_max_tokens_for_node(node: dict) -> int:
    """Resolve response token limit for a node (per-node override first, then prompt_mode default)."""
    from ..config import DEFAULT_AGENTIC_LLM_MAX_TOKENS, DEFAULT_SIMPLE_LLM_MAX_TOKENS
    from .llm_limits import cap_completion_tokens

    raw = node.get("max_tokens")
    try:
        parsed = int(raw) if raw is not None and str(raw).strip() else 0
    except (TypeError, ValueError):
        parsed = 0
    if parsed > 0:
        budget = parsed
    else:
        mode = (node.get("prompt_mode") or "agentic").strip().lower()
        budget = DEFAULT_SIMPLE_LLM_MAX_TOKENS if mode == "simple" else DEFAULT_AGENTIC_LLM_MAX_TOKENS
    return cap_completion_tokens(resolve_model_spec_for_node(node), budget)


def resolve_overflow_model_spec() -> str | None:
    """Return the configured overflow-fallback model for the active profile, or None if disabled."""
    from ..config import MODEL_PROFILES

    profile = resolve_active_profile()
    spec = MODEL_PROFILES[profile].get("overflow")
    s = (spec or "").strip() if isinstance(spec, str) else ""
    return s or None


_CONTEXT_OVERFLOW_MARKERS = (
    "maximum context length",
    "context_length_exceeded",
    "context length is",
    "reduce the length of the messages",
    "string too long",  # some OpenAI-compatible providers phrase it this way
)

_TPM_REQUEST_TOO_LARGE_MARKERS = (
    "tokens per min (tpm)",
    "request too large for gpt",
    '"code": \'rate_limit_exceeded\'',
    "rate_limit_exceeded",
)


_TRANSIENT_LLM_MARKERS = (
    "status_code: 502",
    "status_code: 503",
    "status_code: 504",
    "gateway time-out",
    "gateway timeout",
    "bad gateway",
    "service unavailable",
    "invalid message content type",
    "<nil>",
    "connection reset",
    "connection error",
    "connect timeout",
    "read timeout",
)


def is_transient_llm_error(exc: BaseException) -> bool:
    """True for gateway overload, timeouts, and vLLM nil-content glitches worth retrying."""
    msg = f"{type(exc).__name__}: {exc}".lower()
    if any(marker in msg for marker in _TRANSIENT_LLM_MARKERS):
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        inner = body.get("message") if isinstance(body.get("message"), str) else str(body)
        if any(marker in inner.lower() for marker in _TRANSIENT_LLM_MARKERS):
            return True
    if isinstance(body, str) and any(marker in body.lower() for marker in _TRANSIENT_LLM_MARKERS):
        return True
    return False


def transient_retry_delay_sec(attempt: int) -> float:
    """Exponential backoff for transient LLM failures (attempt is 1-based)."""
    return min(45.0, float(2 ** max(0, attempt - 1)))


_simple_llm_parallel_semaphore: asyncio.Semaphore | None = None


def _get_simple_llm_parallel_semaphore() -> asyncio.Semaphore:
    """Process-wide cap on concurrent simple LLM HTTP calls (parallel PubMed waves)."""
    global _simple_llm_parallel_semaphore
    if _simple_llm_parallel_semaphore is None:
        from ..config import SIMPLE_LLM_PARALLEL_CONCURRENCY

        _simple_llm_parallel_semaphore = asyncio.Semaphore(SIMPLE_LLM_PARALLEL_CONCURRENCY)
    return _simple_llm_parallel_semaphore


def reset_simple_llm_parallel_semaphore_for_tests() -> None:
    """Clear cached semaphore (unit tests only)."""
    global _simple_llm_parallel_semaphore
    _simple_llm_parallel_semaphore = None


def is_tpm_request_too_large_error(exc: BaseException) -> bool:
    """True when a single request exceeds the org TPM/token burst limit (OpenAI 429)."""
    msg = f"{type(exc).__name__}: {exc}".lower()
    if any(marker in msg for marker in _TPM_REQUEST_TOO_LARGE_MARKERS):
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        inner = body.get("message") if isinstance(body.get("message"), str) else str(body)
        if any(marker in inner.lower() for marker in _TPM_REQUEST_TOO_LARGE_MARKERS):
            return True
    return False


def tpm_retry_delay_sec(attempt: int) -> float:
    """Wait for TPM window to reset before retrying oversized requests."""
    return min(90.0, 15.0 * float(max(1, attempt)))


def is_context_overflow_error(exc: BaseException) -> bool:
    """Detect context-length-exceeded errors across OpenAI / DeepSeek / pydantic_ai wrappers."""
    msg = f"{type(exc).__name__}: {exc}".lower()
    if any(marker in msg for marker in _CONTEXT_OVERFLOW_MARKERS):
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        inner = body.get("message") if isinstance(body.get("message"), str) else str(body)
        if any(marker in inner.lower() for marker in _CONTEXT_OVERFLOW_MARKERS):
            return True
    return False


async def run_llm_simple_async(
    *,
    system_prompt: str,
    user_prompt: str,
    result_type: Type[BaseModel],
    model_spec: str,
    max_tokens: int,
    max_retry: int,
    store: dict,
    event_queue: Queue | None,
    node_id: str,
    emit_fn: Any,
    poison_store_on_failure: bool = True,
    sse_kind: str = "llm_simple",
) -> dict[str, Any]:
    """
    Run structured LLM (no tools). Returns validated dict (model_dump).
    On repeated failures: by default sets store['error'] and returns {}.
    poison_store_on_failure=False: do not set store['error'] (e.g. agentic step close path).
    sse_kind: 'kind' field used for emitted SSE events (defaults to 'llm_simple').
    """
    attempt = 0
    extra = ""
    last_err: str | None = None
    tries = max(1, int(max_retry) if max_retry else 3)
    active_spec = model_spec
    overflow_used = False

    from ..engine.prompt_formatting import prepare_llm_message_text

    sys_clean = prepare_llm_message_text(system_prompt)
    user_clean = prepare_llm_message_text(user_prompt)

    while attempt < tries:
        attempt += 1
        full_user = prepare_llm_message_text(user_clean + extra)
        agent = agent_module.get_simple_structured_agent(
            sys_clean,
            result_type,
            model_spec=active_spec,
            max_tokens=max_tokens,
        )
        try:
            # Cap the call to avoid infinite hangs on OpenAI / library loops.
            _LLM_CALL_TIMEOUT_SEC = SIMPLE_LLM_CALL_TIMEOUT_SEC
            try:
                async with _get_simple_llm_parallel_semaphore():
                    res = await asyncio.wait_for(
                        agent.run(full_user),
                        timeout=_LLM_CALL_TIMEOUT_SEC,
                    )
            except asyncio.TimeoutError:
                last_err = f"TimeoutError: agent.run exceeded {_LLM_CALL_TIMEOUT_SEC:.0f}s (check network / OpenAI / proxy)"
                emit_fn(
                    event_queue,
                    {
                        "kind": sse_kind,
                        "node_id": node_id,
                        "attempt": attempt,
                        "ok": False,
                        "error": last_err,
                    },
                )
                if attempt < tries:
                    delay = transient_retry_delay_sec(attempt)
                    emit_fn(
                        event_queue,
                        {
                            "kind": "sys",
                            "text": (
                                f"[SYSTEM] Node {node_id}: LLM call timed out; "
                                f"retrying in {delay:.0f}s ({attempt}/{tries})."
                            ),
                        },
                    )
                    await asyncio.sleep(delay)
                    extra = ""
                    continue
            out = getattr(res, "output", None)
            if out is None:
                out = getattr(res, "data", None)
            if isinstance(out, BaseModel):
                data = out.model_dump()
                emit_fn(
                    event_queue,
                    {"kind": sse_kind, "node_id": node_id, "attempt": attempt, "ok": True},
                )
                return data
            if isinstance(out, dict):
                emit_fn(
                    event_queue,
                    {"kind": sse_kind, "node_id": node_id, "attempt": attempt, "ok": True},
                )
                return out
            last_err = "Empty or invalid structured output"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            emit_fn(
                event_queue,
                {
                    "kind": sse_kind,
                    "node_id": node_id,
                    "attempt": attempt,
                    "ok": False,
                    "error": last_err,
                },
            )
            if not overflow_used and is_context_overflow_error(e):
                overflow_spec = resolve_overflow_model_spec()
                if overflow_spec and overflow_spec != active_spec:
                    overflow_used = True
                    emit_fn(
                        event_queue,
                        {
                            "kind": "sys",
                            "text": (
                                f"[SYSTEM] Node {node_id}: context overflow on {active_spec}; "
                                f"retrying on overflow model {overflow_spec}."
                            ),
                        },
                    )
                    active_spec = overflow_spec
                    extra = ""
                    continue
            if is_tpm_request_too_large_error(e) and attempt < tries:
                delay = tpm_retry_delay_sec(attempt)
                emit_fn(
                    event_queue,
                    {
                        "kind": "sys",
                        "text": (
                            f"[SYSTEM] Node {node_id}: OpenAI TPM/request-size limit; "
                            f"retrying in {delay:.0f}s ({attempt}/{tries}). "
                            "If this persists, lower PUBMED_TOOL_MAX_ANALYZE or raise OpenAI tier."
                        ),
                    },
                )
                await asyncio.sleep(delay)
                extra = ""
                continue
            if is_transient_llm_error(e) and attempt < tries:
                delay = transient_retry_delay_sec(attempt)
                emit_fn(
                    event_queue,
                    {
                        "kind": "sys",
                        "text": (
                            f"[SYSTEM] Node {node_id}: transient LLM error; "
                            f"retrying in {delay:.0f}s ({attempt}/{tries})."
                        ),
                    },
                )
                await asyncio.sleep(delay)
                extra = ""
                continue
        extra = (
            f"\n\n[Retry {attempt}/{tries}] Your previous response did not match the required schema. "
            f"Error: {last_err}. Respond again with ONLY valid structured fields."
        )

    msg = f"Structured LLM node {node_id}: failed after {tries} attempts: {last_err}"
    if poison_store_on_failure:
        store["error"] = msg
        emit_fn(event_queue, {"kind": "sys", "text": f"[SYSTEM] {store['error']}"})
    else:
        emit_fn(
            event_queue,
            {"kind": "sys", "text": f"[SYSTEM] {msg} (flow step continued without full step_close)."},
        )
    return {}
