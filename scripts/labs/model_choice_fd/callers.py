"""The model calls behind every arm. Only this layer differs between arms; prompts, inputs and output validation are the product's.

- ``ClaudeCaller`` is the thinnest Anthropic adapter the experiment needs: one streamed Messages call with the product's own Pydantic output schema as a JSON-schema response format, then the product's own Pydantic validation. It deliberately sends no server-side ``fallbacks``: a refusal by a safety classifier is a result to record, not to route around.
- ``ProductCaller`` runs the shipped model through the product's own runner (``run_llm_simple_async``), with its retry policy, and only replaces the token-ledger side effect with an in-memory capture.
- ``StubCaller`` answers with canned, schema-valid output and calls nothing; it exists for the dry run and the tests.

Every caller returns the same call record, so scoring never needs to know which one ran.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from pydantic import BaseModel, ValidationError

from .common import sha256_text
from .pricing import Ledger, call_cost, worst_case_cost

# A model that always reasons spends part of max_tokens thinking. The product already has a rule for that on its direct path (backend/agents/simple_runner.py, _run_direct_openai): max(node budget x 4, 16000). The Claude adapter uses the same rule, so it is the product's convention for reasoning models, not a value tuned for this experiment.
REASONING_BUDGET_FACTOR = 4
REASONING_BUDGET_FLOOR = 16_000

_TRUNCATION_MARKERS = ("unterminated string", "eof while parsing", "unexpected end", "finish_reason=length", "finish_reason': 'length", "max_tokens", "incomplete")


def reasoning_max_tokens(product_max_tokens: int) -> int:
    return max(int(product_max_tokens) * REASONING_BUDGET_FACTOR, REASONING_BUDGET_FLOOR)


def classify_error_text(text: str) -> str:
    low = (text or "").lower()
    if any(m in low for m in _TRUNCATION_MARKERS):
        return "truncated_or_invalid_json"
    if "validation" in low or "schema" in low:
        return "schema_validation"
    if "timeout" in low or "timed out" in low:
        return "timeout"
    if "429" in low or "rate" in low:
        return "rate_limited"
    return "other"


def _record(provider: str, model: str, *, system: str, user: str, result_type: type[BaseModel], max_tokens: int, effort: str | None, unit: str) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "unit": unit,
        "request": {
            "max_tokens": max_tokens,
            "effort": effort,
            "thinking": "adaptive (model default, not sent)" if provider == "anthropic" else None,
            "schema": result_type.__name__,
            "system_sha256": sha256_text(system),
            "user_sha256": sha256_text(user),
            "prompt_chars": len(system) + len(user),
        },
        "ok": False,
        "output": None,
        "raw_text": None,
        "stop_reason": None,
        "refusal": None,
        "error": None,
        "usage": {},
        "latency_ms": None,
        "cost_usd": None,
        "cost_usd_uncached": None,
        "attempts": [],
        "first_attempt_ok": False,
    }


def validate_output(result_type: type[BaseModel], text: str) -> tuple[dict | None, str | None]:
    """The product's own validation of a JSON answer: parse, then the Pydantic model the node uses."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"json: {exc.msg} at char {exc.pos}"
    try:
        return result_type.model_validate(data).model_dump(), None
    except ValidationError as exc:
        return None, f"validation: {str(exc)[:400]}"


class ClaudeCaller:
    provider = "anthropic"

    def __init__(self, model: str, *, effort: str, api_key: str, ledger: Ledger, run_name: str = "", timeout_sec: float = 600.0, http_client=None) -> None:
        import anthropic

        self.model = model
        self.effort = effort
        self.ledger = ledger
        self.run_name = run_name
        self._anthropic = anthropic
        # The key is always passed explicitly, so the SDK never falls back to another credential from the environment or a login profile. http_client exists for the offline adapter test.
        extra = {"http_client": http_client} if http_client is not None else {}
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=timeout_sec, **extra)

    @property
    def label(self) -> str:
        return self.model

    async def structured(self, *, system: str, user: str, result_type: type[BaseModel], product_max_tokens: int, max_retry: int = 1, unit: str = "", cache: bool = False, timeout_sec: float | None = None) -> dict[str, Any]:
        max_tokens = reasoning_max_tokens(product_max_tokens)
        work = asyncio.to_thread(self._call_sync, system, user, result_type, max_tokens, unit, cache)
        if timeout_sec is None:
            return await work
        try:
            return await asyncio.wait_for(work, timeout=timeout_sec)
        except TimeoutError:
            rec = _record(self.provider, self.model, system=system, user=user, result_type=result_type, max_tokens=max_tokens, effort=self.effort, unit=unit)
            rec["error"] = {"type": "timeout", "kind": "timeout", "message": f"exceeded the product's {timeout_sec:.0f}s timeout"}
            rec["latency_ms"] = int(timeout_sec * 1000)
            rec["attempts"] = [{"ok": False, "error": "timeout"}]
            return rec

    def _call_sync(self, system: str, user: str, result_type: type[BaseModel], max_tokens: int, unit: str, cache: bool) -> dict[str, Any]:
        anthropic = self._anthropic
        rec = _record(self.provider, self.model, system=system, user=user, result_type=result_type, max_tokens=max_tokens, effort=self.effort, unit=unit)
        reserved = worst_case_cost(self.model, len(system) + len(user), max_tokens)
        self.ledger.reserve(reserved)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": self.effort, "format": {"type": "json_schema", "schema": anthropic.transform_schema(result_type)}},
        }
        if system.strip():
            kwargs["system"] = system
        if cache:
            kwargs["cache_control"] = {"type": "ephemeral"}
        rec["request"]["cache"] = cache
        started = time.monotonic()
        message = None
        try:
            with self.client.messages.stream(**kwargs) as stream:
                message = stream.get_final_message()
        except anthropic.APIStatusError as exc:
            rec["error"] = {"type": type(exc).__name__, "status": exc.status_code, "kind": "api_error", "message": str(getattr(exc, "message", exc))[:300]}
        except anthropic.APIConnectionError as exc:
            rec["error"] = {"type": type(exc).__name__, "kind": "connection", "message": str(exc)[:300]}
        except Exception as exc:  # noqa: BLE001 - recorded as an error trial; the reservation must still be released below
            rec["error"] = {"type": type(exc).__name__, "kind": "other", "message": str(exc)[:300]}
        rec["latency_ms"] = round((time.monotonic() - started) * 1000)
        cost = None
        if message is not None:
            u = message.usage
            rec["usage"] = {
                "input_tokens": getattr(u, "input_tokens", None),
                "output_tokens": getattr(u, "output_tokens", None),
                "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", None),
                "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", None),
            }
            cost, uncached = call_cost(self.model, rec["usage"])
            rec["cost_usd"], rec["cost_usd_uncached"] = cost, uncached
            rec["stop_reason"] = message.stop_reason
            rec["request_id"] = getattr(message, "_request_id", None)
            rec["raw_text"] = "".join(getattr(b, "text", "") for b in message.content if getattr(b, "type", "") == "text")
            if message.stop_reason == "refusal":
                details = getattr(message, "stop_details", None)
                rec["refusal"] = {"category": getattr(details, "category", None), "explanation": getattr(details, "explanation", None)}
                rec["error"] = {"type": "refusal", "kind": "refusal", "message": str(rec["refusal"]["category"])}
            else:
                output, problem = validate_output(result_type, rec["raw_text"])
                if output is not None:
                    rec["ok"], rec["output"] = True, output
                else:
                    kind = "truncated" if message.stop_reason == "max_tokens" else "schema_validation"
                    rec["error"] = {"type": kind, "kind": kind, "message": problem}
        self.ledger.settle(reserved, {"run": self.run_name, "model": self.model, "unit": unit, "cost_usd": cost or 0.0, "stop_reason": rec["stop_reason"], "error": (rec["error"] or {}).get("type")})
        rec["attempts"] = [{"ok": rec["ok"], "error": (rec["error"] or {}).get("kind")}]
        rec["first_attempt_ok"] = rec["ok"]
        return rec


# --- the shipped model, through the product's own runner ------------------------------------------------------------

_usage_sink: ContextVar[list | None] = ContextVar("model_choice_fd_usage_sink", default=None)
_patched = {"done": False}


def _capture_usage(store: dict, res: Any, model_spec: str) -> None:
    """Replaces the runner's token-ledger write (a database insert) with an in-memory record."""
    sink = _usage_sink.get()
    if sink is None:
        return
    from backend.research_queue.token_budget import extract_usage

    prompt, completion, total = extract_usage(res)
    sink.append({"input_tokens": prompt, "output_tokens": completion, "total_tokens": total, "model_spec": model_spec})


def install_product_patches() -> None:
    if _patched["done"]:
        return
    from backend.agents import simple_runner

    simple_runner._record_token_usage_from_store = _capture_usage
    _patched["done"] = True


class ProductCaller:
    provider = "product-runner"

    def __init__(self, model_spec: str) -> None:
        install_product_patches()
        self.model = model_spec
        self.effort = None

    @property
    def label(self) -> str:
        return self.model

    async def structured(self, *, system: str, user: str, result_type: type[BaseModel], product_max_tokens: int, max_retry: int = 3, unit: str = "", cache: bool = False, timeout_sec: float | None = None) -> dict[str, Any]:
        from backend.agents.simple_runner import run_llm_simple_async
        from backend.config import QUALITY_FIRST_HARD_MODE, QUALITY_FIRST_MAX_RETRY

        tries = max(int(max_retry), QUALITY_FIRST_MAX_RETRY) if QUALITY_FIRST_HARD_MODE else int(max_retry)
        rec = _record(self.provider, self.model, system=system, user=user, result_type=result_type, max_tokens=product_max_tokens, effort=None, unit=unit)
        rec["request"]["max_retry"] = tries
        events: list[dict] = []
        usage: list[dict] = []
        store: dict[str, Any] = {}
        token = _usage_sink.set(usage)
        started = time.monotonic()
        try:
            out = await run_llm_simple_async(
                system_prompt=system,
                user_prompt=user,
                result_type=result_type,
                model_spec=self.model,
                max_tokens=product_max_tokens,
                max_retry=tries,
                store=store,
                event_queue=None,
                node_id=unit or "experiment",
                emit_fn=lambda _queue, payload: events.append(dict(payload)),
            )
        finally:
            _usage_sink.reset(token)
        rec["latency_ms"] = round((time.monotonic() - started) * 1000)
        rec["attempts"] = [{"ok": bool(e.get("ok")), "error": classify_error_text(str(e.get("error") or "")) if not e.get("ok") else None, "detail": str(e.get("error") or "")[:400] or None} for e in events if e.get("kind") == "llm_simple" and "attempt" in e and "ok" in e]
        rec["first_attempt_ok"] = bool(rec["attempts"] and rec["attempts"][0]["ok"])
        if usage:
            rec["usage"] = {"input_tokens": sum(int(u.get("input_tokens") or 0) for u in usage), "output_tokens": sum(int(u.get("output_tokens") or 0) for u in usage)}
        if out:
            rec["ok"], rec["output"] = True, out
            rec["raw_text"] = json.dumps(out, ensure_ascii=False)
            rec["stop_reason"] = "end_turn"
        else:
            message = str(store.get("error") or "no output")
            rec["error"] = {"type": "product_runner_failed", "kind": classify_error_text(message), "message": message[:600]}
        return rec


# --- the dry run -------------------------------------------------------------------------------------------------------

class StubCaller:
    """Canned, schema-valid answers from ``make(result_type, unit, user)``; calls nothing and costs nothing."""

    provider = "stub"

    def __init__(self, make: Callable[[type[BaseModel], str, str], dict], label: str = "stub") -> None:
        self.make = make
        self.model = label
        self.effort = None

    @property
    def label(self) -> str:
        return self.model

    async def structured(self, *, system: str, user: str, result_type: type[BaseModel], product_max_tokens: int, max_retry: int = 1, unit: str = "", cache: bool = False, timeout_sec: float | None = None) -> dict[str, Any]:
        rec = _record(self.provider, self.model, system=system, user=user, result_type=result_type, max_tokens=product_max_tokens, effort=None, unit=unit)
        output, problem = validate_output(result_type, json.dumps(self.make(result_type, unit, user)))
        rec.update({"ok": output is not None, "output": output, "raw_text": json.dumps(output) if output else None, "stop_reason": "end_turn", "latency_ms": 0, "usage": {"input_tokens": 0, "output_tokens": 0}, "cost_usd": 0.0, "cost_usd_uncached": 0.0})
        if problem:
            rec["error"] = {"type": "schema_validation", "kind": "schema_validation", "message": problem}
        rec["attempts"] = [{"ok": rec["ok"], "error": None if rec["ok"] else "schema_validation"}]
        rec["first_attempt_ok"] = rec["ok"]
        return rec
