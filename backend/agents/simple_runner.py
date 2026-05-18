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
from ..engine.prompt_formatting import prepare_llm_message_text

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
                extra = (
                    f"\n\n[Retry {attempt}/{tries}] Your previous response did not match the required schema. "
                    f"Error: {last_err}. Respond again with ONLY valid structured fields."
                )
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
