"""The Claude adapter of the guideline-points pipeline (it implements ``ports.PointsCaller``), the model specs and the one price table, made the way production calls Claude (ADR 006).

The request is built by the production adapter (``backend.agents.anthropic_direct.build_request``: the Pydantic schema as a JSON-schema response format, a pinned effort, adaptive thinking by default, the server-side refusal fallback) and the answer is validated by its ``parse_message``. Two things are added here, because the adapter's one-shot ``call_structured`` has no room for them:

- the documents go in their own content block with a cache breakpoint, so the revision rounds of one disease read the shelf from the prompt cache instead of paying for it again;
- every call returns its full token usage (fresh, cache write, cache read, output) and passes through an optional budget, so a lab can cap spend and report cost per disease.

An answer that fails is returned as a record with ``ok: False`` and the error; nothing is raised into the loop, which treats a failed call as a failed step, never as a pass.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import anthropic
from pydantic import BaseModel

from ...agents.anthropic_direct import ClaudeCallError, build_request, parse_message, parse_spec, reasoning_max_tokens
from ...research_queue.token_budget import record_usage
from .ports import Budget

log = logging.getLogger(__name__)

GENERATOR_SPEC = "anthropic:claude-sonnet-5-5@high"
VERIFIER_SPEC = "anthropic:claude-opus-5-5@high"
# Node budgets before the reasoning rule (x4, floor 16000): the generator writes up to six points in two languages; the verifier one verdict per point.
GENERATOR_NODE_TOKENS = 8_000
VERIFIER_NODE_TOKENS = 6_000


# USD per million tokens: (input, output, cache read, cache write).
PRICES: dict[str, tuple[float, float, float, float]] = {"claude-opus-5-5": (4.0, 20.0, 0.20, 5.0), "claude-sonnet-5-5": (2.0, 10.0, 0.10, 2.5)}


def call_cost(model: str, usage: dict[str, Any]) -> float | None:
    """What one call cost in USD, from its token usage; None for a model without a price."""
    price = PRICES.get(model)
    if price is None:
        return None
    pin, pout, pread, pwrite = price
    return (int(usage.get("input_tokens", 0) or 0) * pin + int(usage.get("cache_creation_input_tokens", 0) or 0) * pwrite + int(usage.get("cache_read_input_tokens", 0) or 0) * pread + int(usage.get("output_tokens", 0) or 0) * pout) / 1_000_000


def _usage(message: Any) -> dict[str, int]:
    u = getattr(message, "usage", None)
    return {name: int(getattr(u, name, 0) or 0) for name in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}


class ClaudePointsCaller:
    """One role (generator or verifier) bound to one Claude model spec."""

    # Seconds a call may take, and how many times a retryable failure is retried, on top of the SDK's own two retries.
    TIMEOUT_SEC = 900.0
    RETRIES = 1

    def __init__(self, spec: str, *, api_key: str, node_max_tokens: int, budget: Budget | None = None, client: Any = None) -> None:
        self.spec = spec
        self.model, self.effort = parse_spec(spec)
        self.max_tokens = reasoning_max_tokens(node_max_tokens)
        self.budget = budget
        self.retries = self.RETRIES
        if client is None:
            # The key is passed explicitly so the SDK never falls back to another credential in the environment.
            client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=2, timeout=self.TIMEOUT_SEC)
        self.client = client

    def _request(self, system: str, prefix: str, user: str, result_type: type[BaseModel], cache: bool = True) -> dict[str, Any]:
        kwargs = build_request(model=self.model, effort=self.effort, system_prompt=system, user_prompt=user, result_type=result_type, max_tokens=self.max_tokens)
        if prefix:
            first: dict[str, Any] = {"type": "text", "text": prefix}
            if cache:
                first["cache_control"] = {"type": "ephemeral"}
            kwargs["messages"] = [{"role": "user", "content": [first, {"type": "text", "text": user}]}]
        return kwargs

    async def call(self, *, role: str, system: str, prefix: str, user: str, result_type: type[BaseModel], cache: bool = True) -> tuple[BaseModel | None, dict[str, Any]]:
        attempts: list[dict[str, Any]] = []
        output: BaseModel | None = None
        for _ in range(1 + max(0, self.retries)):
            output, attempt = await self._once(role, system, prefix, user, result_type, cache)
            attempts.append(attempt)
            if output is not None or not attempt.get("retryable"):
                break
        record = dict(attempts[-1])
        record["attempts"] = attempts
        record["usage_total"] = {k: sum(int(a["usage"].get(k, 0)) for a in attempts) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}
        costs = [a.get("cost_usd") for a in attempts]
        record["cost_usd_total"] = None if any(c is None for c in costs) else sum(costs)
        return output, record

    async def _once(self, role: str, system: str, prefix: str, user: str, result_type: type[BaseModel], cache: bool = True) -> tuple[BaseModel | None, dict[str, Any]]:
        kwargs = self._request(system, prefix, user, result_type, cache)
        prompt_chars = len(system) + len(prefix) + len(user)
        record: dict[str, Any] = {
            "role": role, "model": self.model, "effort": self.effort, "max_tokens": self.max_tokens, "prompt_chars": prompt_chars,
            "ok": False, "error": None, "retryable": False, "stop_reason": None, "served_by": None, "request_id": None,
            "usage": {}, "cost_usd": None, "latency_ms": None, "output": None, "raw_text": None,
        }
        ticket = self.budget.reserve(self.model, prompt_chars, self.max_tokens) if self.budget else None
        started = time.monotonic()
        message = None
        try:
            async with self.client.messages.stream(**kwargs) as stream:
                message = await stream.get_final_message()
        except anthropic.APIStatusError as exc:
            err = ClaudeCallError("api", f"{self.model} HTTP {exc.status_code}: {str(getattr(exc, 'message', exc))[:300]}", status_code=exc.status_code)
            record["error"], record["retryable"] = {"kind": err.kind, "message": str(err), "status": exc.status_code}, err.retryable
        except anthropic.APIConnectionError as exc:
            record["error"], record["retryable"] = {"kind": "api", "message": f"connection error: {str(exc)[:300]}"}, True
        except Exception as exc:  # noqa: BLE001 - recorded as a failed call; the reservation is settled below
            record["error"] = {"kind": "other", "message": f"{type(exc).__name__}: {str(exc)[:300]}"}
        record["latency_ms"] = round((time.monotonic() - started) * 1000)
        output: BaseModel | None = None
        if message is not None:
            record["usage"] = _usage(message)
            record["stop_reason"] = getattr(message, "stop_reason", None)
            record["served_by"] = str(getattr(message, "model", "") or "") or None
            record["request_id"] = getattr(message, "_request_id", None)
            record["raw_text"] = "".join(getattr(b, "text", "") for b in (getattr(message, "content", None) or []) if getattr(b, "type", "") == "text")
            try:
                output = parse_message(message, result_type).output
                record["ok"], record["output"] = True, output.model_dump()
            except ClaudeCallError as exc:
                record["error"], record["retryable"] = {"kind": exc.kind, "message": str(exc)}, exc.retryable
        if self.budget:
            record["cost_usd"] = self.budget.settle(ticket, self.model, record["usage"], role, (record["error"] or {}).get("kind"))
        return output, record


class LedgerBudget:
    """Production ``Budget``: records each Claude call in the research token ledger (``token_usage``) and returns its cost. It refuses no single call; the service checks the monthly guard once, before a run starts."""

    def __init__(self, slug: str, execution_id: str) -> None:
        self.slug, self.execution_id = slug, execution_id

    def reserve(self, model: str, prompt_chars: int, max_tokens: int) -> None:
        return None

    def settle(self, ticket: Any, model: str, usage: dict[str, Any], role: str, error: str | None) -> float | None:
        try:
            prompt = sum(int(usage.get(k, 0) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            completion = int(usage.get("output_tokens", 0) or 0)
            record_usage(execution_id=self.execution_id, model_spec=f"anthropic:{model}", prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion, disease_slug=self.slug)
        except Exception:  # token capture must never break a run
            log.debug("guideline points: token usage not recorded", exc_info=True)
        return call_cost(model, usage)


def claude_callers(slug: str, execution_id: str) -> tuple[ClaudePointsCaller, ClaudePointsCaller, str]:
    """The production generator and verifier for one run, spending into the research ledger, and a label of the models for the stored row."""
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; guideline points run on Claude only (ADR 006)")
    budget = LedgerBudget(slug, execution_id)
    generator = ClaudePointsCaller(GENERATOR_SPEC, api_key=key, node_max_tokens=GENERATOR_NODE_TOKENS, budget=budget)
    verifier = ClaudePointsCaller(VERIFIER_SPEC, api_key=key, node_max_tokens=VERIFIER_NODE_TOKENS, budget=budget)
    return generator, verifier, f"generator {GENERATOR_SPEC}; verifier and coverage {VERIFIER_SPEC}"
