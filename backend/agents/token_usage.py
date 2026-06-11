"""Aggregate LLM token usage from Pydantic AI RunUsage across a pipeline run."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from pydantic_ai.usage import RunUsage

_LOGGER = logging.getLogger(__name__)

_LEDGER_STORE_KEY = "_token_ledger"


@dataclass(frozen=True)
class TokenUsageSnapshot:
    """Immutable record of token usage for one LLM API interaction."""

    node_id: str
    model_spec: str
    prompt_mode: str
    attempt: int
    input_tokens: int
    output_tokens: int
    requests: int
    tool_calls: int
    cache_read_tokens: int
    cache_write_tokens: int
    duration_ms: int | None
    ok: bool
    usage_reported: bool


def _usage_fields(usage: RunUsage | None) -> dict[str, int]:
    if usage is None:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "requests": 0,
            "tool_calls": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "requests": int(getattr(usage, "requests", 0) or 0),
        "tool_calls": int(getattr(usage, "tool_calls", 0) or 0),
        "cache_read_tokens": int(getattr(usage, "cache_read_tokens", 0) or 0),
        "cache_write_tokens": int(getattr(usage, "cache_write_tokens", 0) or 0),
    }


def _usage_reported(fields: dict[str, int]) -> bool:
    return (fields["input_tokens"] + fields["output_tokens"]) > 0


def snapshot_from_usage(
    usage: RunUsage | None,
    *,
    node_id: str,
    model_spec: str,
    prompt_mode: str,
    attempt: int = 1,
    duration_ms: int | None = None,
    ok: bool = True,
) -> TokenUsageSnapshot:
    """Build a snapshot from Pydantic AI usage (zeros when usage is missing)."""
    fields = _usage_fields(usage)
    return TokenUsageSnapshot(
        node_id=node_id,
        model_spec=model_spec,
        prompt_mode=prompt_mode,
        attempt=max(1, int(attempt)),
        duration_ms=duration_ms,
        ok=ok,
        usage_reported=_usage_reported(fields),
        **fields,
    )


def _snapshot_to_dict(snapshot: TokenUsageSnapshot) -> dict[str, Any]:
    return {
        "node_id": snapshot.node_id,
        "model_spec": snapshot.model_spec,
        "prompt_mode": snapshot.prompt_mode,
        "attempt": snapshot.attempt,
        "input_tokens": snapshot.input_tokens,
        "output_tokens": snapshot.output_tokens,
        "total_tokens": snapshot.input_tokens + snapshot.output_tokens,
        "requests": snapshot.requests,
        "tool_calls": snapshot.tool_calls,
        "cache_read_tokens": snapshot.cache_read_tokens,
        "cache_write_tokens": snapshot.cache_write_tokens,
        "duration_ms": snapshot.duration_ms,
        "ok": snapshot.ok,
        "usage_reported": snapshot.usage_reported,
    }


def _empty_totals() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "requests": 0,
        "tool_calls": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "calls": 0,
    }


def _incr_totals(totals: dict[str, int], snapshot: TokenUsageSnapshot) -> dict[str, int]:
    return {
        "input_tokens": totals["input_tokens"] + snapshot.input_tokens,
        "output_tokens": totals["output_tokens"] + snapshot.output_tokens,
        "requests": totals["requests"] + snapshot.requests,
        "tool_calls": totals["tool_calls"] + snapshot.tool_calls,
        "cache_read_tokens": totals["cache_read_tokens"] + snapshot.cache_read_tokens,
        "cache_write_tokens": totals["cache_write_tokens"] + snapshot.cache_write_tokens,
        "calls": totals["calls"] + 1,
    }


class RunTokenLedger:
    """Thread-safe accumulator of token usage snapshots for one pipeline run."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshots: list[TokenUsageSnapshot] = []
        self._totals = _empty_totals()
        self._by_node: dict[str, dict[str, int]] = {}
        self._by_model: dict[str, dict[str, int]] = {}

    def record(self, snapshot: TokenUsageSnapshot) -> None:
        """Append a snapshot and update running aggregates."""
        with self._lock:
            self._snapshots.append(snapshot)
            self._totals = _incr_totals(self._totals, snapshot)
            node_key = snapshot.node_id or "__unknown__"
            model_key = snapshot.model_spec or "__unknown__"
            self._by_node[node_key] = _incr_totals(
                self._by_node.get(node_key, _empty_totals()),
                snapshot,
            )
            self._by_model[model_key] = _incr_totals(
                self._by_model.get(model_key, _empty_totals()),
                snapshot,
            )

    @property
    def call_count(self) -> int:
        with self._lock:
            return len(self._snapshots)

    def totals(self) -> dict[str, int]:
        """Return run-level token totals."""
        with self._lock:
            return dict(self._totals)

    def by_node(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {k: dict(v) for k, v in self._by_node.items()}

    def by_model(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {k: dict(v) for k, v in self._by_model.items()}

    def to_store_payload(self) -> dict[str, Any]:
        """JSON-serializable summary for ``store['token_usage']``."""
        totals = self.totals()
        return {
            "totals": totals,
            "total_tokens": totals["input_tokens"] + totals["output_tokens"],
            "by_node": self.by_node(),
            "by_model": self.by_model(),
            "records": [_snapshot_to_dict(s) for s in self._snapshots_with_lock()],
        }

    def _snapshots_with_lock(self) -> list[TokenUsageSnapshot]:
        with self._lock:
            return list(self._snapshots)

    def flush_to_logs(self, execution_id: str) -> None:
        """Emit a single structured summary log line for the run."""
        if not execution_id:
            return
        try:
            from ..observability.run_log import log_token_usage
        except ImportError:
            from observability.run_log import log_token_usage

        totals = self.totals()
        log_token_usage(
            "token_usage_summary",
            execution_id=execution_id,
            input_tokens=totals["input_tokens"],
            output_tokens=totals["output_tokens"],
            total_tokens=totals["input_tokens"] + totals["output_tokens"],
            calls=totals["calls"],
            requests=totals["requests"],
            tool_calls=totals["tool_calls"],
            by_node=self.by_node(),
            by_model=self.by_model(),
        )


def ledger_for_store(store: dict[str, Any]) -> RunTokenLedger:
    """Return (or create) the token ledger attached to a run ``store``."""
    ledger = store.get(_LEDGER_STORE_KEY)
    if isinstance(ledger, RunTokenLedger):
        return ledger
    ledger = RunTokenLedger()
    store[_LEDGER_STORE_KEY] = ledger
    return ledger


def record_from_pydantic_usage(
    usage: RunUsage | None,
    *,
    ledger: RunTokenLedger,
    node_id: str,
    model_spec: str,
    prompt_mode: str,
    attempt: int = 1,
    duration_ms: int | None = None,
    ok: bool = True,
    execution_id: str | None = None,
    log_record: bool = True,
) -> TokenUsageSnapshot | None:
    """Record provider usage on the ledger (fail-open)."""
    try:
        snapshot = snapshot_from_usage(
            usage,
            node_id=node_id,
            model_spec=model_spec,
            prompt_mode=prompt_mode,
            attempt=attempt,
            duration_ms=duration_ms,
            ok=ok,
        )
        ledger.record(snapshot)
        if log_record and execution_id:
            try:
                from ..observability.run_log import log_token_usage
            except ImportError:
                from observability.run_log import log_token_usage

            log_token_usage(
                "token_usage_record",
                execution_id=execution_id,
                node_id=node_id,
                model_spec=model_spec,
                prompt_mode=prompt_mode,
                attempt=attempt,
                input_tokens=snapshot.input_tokens,
                output_tokens=snapshot.output_tokens,
                total_tokens=snapshot.input_tokens + snapshot.output_tokens,
                requests=snapshot.requests,
                tool_calls=snapshot.tool_calls,
                usage_reported=snapshot.usage_reported,
                ok=ok,
                duration_ms=duration_ms,
            )
        return snapshot
    except Exception:
        _LOGGER.warning("token usage recording failed", exc_info=True)
        return None


def finalize_token_usage_for_store(store: dict[str, Any]) -> None:
    """Write ``store['token_usage']`` and emit summary logs when a run ends."""
    ledger = store.get(_LEDGER_STORE_KEY)
    if not isinstance(ledger, RunTokenLedger):
        return
    store["token_usage"] = ledger.to_store_payload()
    execution_id = str(store.get("execution_id") or "").strip()
    if execution_id:
        try:
            ledger.flush_to_logs(execution_id)
        except Exception:
            _LOGGER.warning("token usage flush_to_logs failed", exc_info=True)
