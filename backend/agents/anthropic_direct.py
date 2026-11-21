"""Structured calls to Claude through the Anthropic Messages API.

Why a direct adapter and not pydantic-ai. The model choice for every step was decided by the FD model-choice lab (``scripts/labs/model_choice_fd/``), and the lab called Claude in one specific way: one streamed Messages call, the node's own Pydantic schema sent as a JSON-schema response format, a pinned ``effort``, the model's default adaptive thinking, and ``max_tokens = max(node budget x 4, 16000)``. Production must call the model the way it was measured, or the measurement says nothing about production. pydantic-ai 1.97.0 is pinned (``mcp`` 2.0 broke the version above it) and routes structured output through a forced tool call, which Claude 5.5 models reject together with thinking. This module is the same small seam ``openai_direct`` already is for OpenAI reasoning models.

Model spec format: ``anthropic:<model>[@<effort>]``, e.g. ``anthropic:claude-sonnet-5-5@high``. Effort defaults to ``medium``, the level the lab pinned for search, the search judge and PubMed; the synthesis spec names ``high``.

Refusals. Claude 5.5 models run safety classifiers (including biology) that can decline a request. Every call opts into Anthropic's server-side fallback (``fallbacks: "default"``), which re-runs a declined request on the model Anthropic recommends for that refusal category, inside the same call and still on Anthropic. A refusal that survives the fallback is raised as ``ClaudeCallError(kind="refusal")`` and never retried. The lab saw 0 refusals in 762 calls on FD content.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Type

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

SPEC_PREFIX = "anthropic:"
DEFAULT_EFFORT = "medium"
EFFORTS = ("low", "medium", "high", "xhigh", "max")

# The rule the lab used and the OpenAI direct path already uses for reasoning models: the model spends part of max_tokens thinking, so the visible answer needs headroom above the node's nominal budget.
REASONING_BUDGET_FACTOR = 4
REASONING_BUDGET_FLOOR = 16_000
# Claude Sonnet 5.5, Opus 5.5 and Haiku 5.5 all accept up to 128K output tokens on the Messages API.
MAX_OUTPUT_TOKENS = 128_000

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeCallError(RuntimeError):
    """A Claude call that produced no usable answer.

    ``kind`` is one of ``config`` (no key), ``api`` (HTTP or connection error after the SDK's own retries), ``refusal`` (declined even after the server-side fallback), ``truncated`` (``max_tokens`` reached before the JSON closed) or ``invalid_output`` (JSON that does not match the node's schema).
    """

    def __init__(self, kind: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        return self.kind in ("truncated", "invalid_output") or (self.kind == "api" and self.status_code not in (400, 401, 403, 404))


@dataclass(frozen=True)
class ClaudeResult:
    output: BaseModel
    model: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    request_id: str | None = None

    @property
    def usage(self) -> tuple[int, int, int]:
        return (self.input_tokens, self.output_tokens, self.input_tokens + self.output_tokens)


def is_anthropic_spec(spec: str | None) -> bool:
    return (spec or "").strip().lower().startswith(SPEC_PREFIX)


def parse_spec(spec: str) -> tuple[str, str]:
    """``anthropic:claude-sonnet-5-5@high`` -> (``claude-sonnet-5-5``, ``high``)."""
    s = (spec or "").strip()
    if not is_anthropic_spec(s):
        raise ValueError(f"Not an Anthropic model spec: {spec!r}")
    body = s[len(SPEC_PREFIX):].strip()
    model, _, effort = body.partition("@")
    model = model.strip()
    effort = (effort.strip().lower() or DEFAULT_EFFORT)
    if not model:
        raise ValueError(f"Anthropic model spec names no model: {spec!r}")
    if effort not in EFFORTS:
        raise ValueError(f"Unknown effort {effort!r} in {spec!r}; expected one of {EFFORTS}")
    return model, effort


_rerouted_specs: set[str] = set()


def enforce_anthropic_only(spec: str | None) -> str:
    """Under MODEL_PROFILE=anthropic, return ``spec`` if it is a Claude spec, else the default Claude spec.

    This is the one choke point that keeps the privacy policy true: a flow row seeded years ago with a Gemma or OpenAI model, or a leftover env var, must not send a user's text to a provider the policy does not name. Outside that profile the spec is returned unchanged.
    """
    from ..config import ANTHROPIC_DEFAULT_SPEC, ANTHROPIC_ONLY

    s = (spec or "").strip()
    if not ANTHROPIC_ONLY or is_anthropic_spec(s):
        return s
    if s not in _rerouted_specs:
        _rerouted_specs.add(s)
        log.warning("anthropic-only: model spec %r is not a Claude model; using %s instead", s, ANTHROPIC_DEFAULT_SPEC)
    return ANTHROPIC_DEFAULT_SPEC


def reasoning_max_tokens(node_budget: int) -> int:
    return min(max(int(node_budget) * REASONING_BUDGET_FACTOR, REASONING_BUDGET_FLOOR), MAX_OUTPUT_TOKENS)


def api_key() -> str:
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def _make_client(key: str, timeout_sec: float):
    import anthropic

    # The key is always passed explicitly, so the SDK never picks up another credential from the environment or a login profile. The SDK retries 408/409/429/5xx and connection errors itself.
    return anthropic.AsyncAnthropic(api_key=key, max_retries=2, timeout=timeout_sec)


def free_form_maps(schema: Any, path: str = "$") -> list[str]:
    """Paths of objects whose keys are not named (``dict[str, X]``, ``additionalProperties`` set to a schema or true).

    Claude's structured output accepts only objects with named properties; the SDK turns such a map into an object that allows no keys, so the model can only answer ``{}`` and the call "succeeds" with nothing in it.
    """
    found: list[str] = []
    if isinstance(schema, dict):
        extra = schema.get("additionalProperties")
        if extra is True or isinstance(extra, dict):
            found.append(path)
        for key, value in schema.items():
            if isinstance(value, (dict, list)):
                found.extend(free_form_maps(value, f"{path}.{key}"))
    elif isinstance(schema, list):
        for i, value in enumerate(schema):
            found.extend(free_form_maps(value, f"{path}[{i}]"))
    return found


def build_request(*, model: str, effort: str, system_prompt: str, user_prompt: str, result_type: Type[BaseModel], max_tokens: int) -> dict[str, Any]:
    import anthropic

    maps = free_form_maps(result_type.model_json_schema())
    if maps:
        raise ClaudeCallError("config", f"{result_type.__name__} has free-form map fields Claude's structured output cannot express ({', '.join(maps[:3])}); use a list of named items instead")

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": user_prompt}],
        "output_config": {
            "effort": effort,
            "format": {"type": "json_schema", "schema": anthropic.transform_schema(result_type)},
        },
        "extra_headers": {"anthropic-beta": FALLBACK_BETA},
        "extra_body": {"fallbacks": "default"},
    }
    if system_prompt.strip():
        kwargs["system"] = system_prompt
    return kwargs


def parse_message(message: Any, result_type: Type[BaseModel]) -> ClaudeResult:
    """Turn a final Message into a validated result, or raise ``ClaudeCallError``."""
    stop_reason = getattr(message, "stop_reason", None)
    usage = getattr(message, "usage", None)
    input_tokens = sum(int(getattr(usage, name, 0) or 0) for name in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    served_by = str(getattr(message, "model", "") or "")
    if stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None)
        raise ClaudeCallError("refusal", f"{served_by or 'Claude'} declined the request (category: {category or 'unspecified'})")
    text = "".join(getattr(block, "text", "") for block in (getattr(message, "content", None) or []) if getattr(block, "type", "") == "text")
    if not text.strip():
        kind = "truncated" if stop_reason == "max_tokens" else "invalid_output"
        raise ClaudeCallError(kind, f"{served_by or 'Claude'} returned no text (stop_reason={stop_reason})")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        kind = "truncated" if stop_reason == "max_tokens" else "invalid_output"
        raise ClaudeCallError(kind, f"JSON: {exc.msg} at char {exc.pos} (stop_reason={stop_reason})") from exc
    try:
        output = result_type.model_validate(data)
    except ValidationError as exc:
        raise ClaudeCallError("invalid_output", f"schema validation: {str(exc)[:400]}") from exc
    return ClaudeResult(
        output=output,
        model=served_by,
        stop_reason=stop_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        request_id=getattr(message, "_request_id", None),
    )


async def call_structured(
    *,
    spec: str,
    system_prompt: str,
    user_prompt: str,
    result_type: Type[BaseModel],
    node_max_tokens: int,
    timeout_sec: float,
    max_tokens_override: int | None = None,
) -> ClaudeResult:
    """One streamed structured call. Raises ``ClaudeCallError`` on any failure."""
    import anthropic

    key = api_key()
    if not key:
        raise ClaudeCallError("config", f"{spec} needs ANTHROPIC_API_KEY")
    model, effort = parse_spec(spec)
    max_tokens = max_tokens_override or reasoning_max_tokens(node_max_tokens)
    kwargs = build_request(model=model, effort=effort, system_prompt=system_prompt, user_prompt=user_prompt, result_type=result_type, max_tokens=max_tokens)
    try:
        async with _make_client(key, timeout_sec) as client:
            async with client.messages.stream(**kwargs) as stream:
                message = await stream.get_final_message()
    except anthropic.APIStatusError as exc:
        raise ClaudeCallError("api", f"{model} HTTP {exc.status_code}: {str(getattr(exc, 'message', exc))[:300]}", status_code=exc.status_code) from exc
    except anthropic.APIConnectionError as exc:
        raise ClaudeCallError("api", f"{model} connection error: {str(exc)[:300]}") from exc
    result = parse_message(message, result_type)
    if result.model and result.model != model:
        log.warning("anthropic_direct: %s declined, answered by fallback %s", model, result.model)
    return result


__all__ = [
    "ClaudeCallError",
    "ClaudeResult",
    "DEFAULT_EFFORT",
    "SPEC_PREFIX",
    "build_request",
    "call_structured",
    "enforce_anthropic_only",
    "is_anthropic_spec",
    "parse_message",
    "parse_spec",
    "reasoning_max_tokens",
]
