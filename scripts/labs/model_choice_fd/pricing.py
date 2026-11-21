"""Prices, cost of one call, and the spend ledger that enforces the experiment's hard cap.

Anthropic prices are the first-party list prices from the claude-api reference (cached 2026-11-03), in USD per million tokens. Cache writes are billed at 1.25x the input price for the default five-minute cache; reads at the listed cache-read price. Gemma on SiliconFlow has no verified price here, so its cost is reported as unknown and only its tokens are recorded.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from .common import LEDGER_FILE, LabError, append_jsonl, now_iso, read_jsonl

DEFAULT_CAP_USD = 20.0


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float
    cache_write: float
    long_input: float | None = None  # price above long_threshold prompt tokens, when the model has one
    long_output: float | None = None
    long_threshold: int | None = None


PRICES: dict[str, Price] = {
    "claude-opus-5-5": Price(input=4.0, output=20.0, cache_read=0.20, cache_write=5.0),
    "claude-sonnet-5-5": Price(input=2.0, output=10.0, cache_read=0.10, cache_write=2.5),
    # Haiku 5.5: $0.10 / $0.50 up to 100K prompt tokens, $0.50 / $2.50 beyond. Its cache-read price is not in the reference; 0.1x input is assumed and marked as such in the report.
    "claude-haiku-5-5": Price(input=0.10, output=0.50, cache_read=0.01, cache_write=0.125, long_input=0.50, long_output=2.50, long_threshold=100_000),
}


def price_for(model: str) -> Price | None:
    return PRICES.get(model)


def call_cost(model: str, usage: dict) -> tuple[float | None, float | None]:
    """(billed cost, the same call's cost with no cache at all). None when the model has no known price."""
    p = price_for(model)
    if p is None:
        return None, None
    fresh = int(usage.get("input_tokens") or 0)
    written = int(usage.get("cache_creation_input_tokens") or 0)
    read = int(usage.get("cache_read_input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    prompt_total = fresh + written + read
    pin, pout, pread, pwrite = p.input, p.output, p.cache_read, p.cache_write
    if p.long_threshold and prompt_total > p.long_threshold:
        scale = (p.long_input or p.input) / p.input
        pin, pout, pread, pwrite = p.long_input or pin, p.long_output or pout, pread * scale, pwrite * scale
    billed = (fresh * pin + written * pwrite + read * pread + out * pout) / 1_000_000
    uncached = (prompt_total * pin + out * pout) / 1_000_000
    return billed, uncached


def worst_case_cost(model: str, prompt_chars: int, max_tokens: int) -> float:
    """Upper bound for one call before it is made: ~3 characters per token for the prompt (conservative for English and JSON) and the whole max_tokens as output."""
    p = price_for(model)
    if p is None:
        return 0.0
    prompt_tokens = prompt_chars / 3.0
    pin, pout = p.input, p.output
    if p.long_threshold and prompt_tokens > p.long_threshold:
        pin, pout = p.long_input or pin, p.long_output or pout
    return (prompt_tokens * pin * 1.25 + max_tokens * pout) / 1_000_000


class Ledger:
    """Cumulative Anthropic spend across every run of the experiment, kept in results/ledger.jsonl."""

    def __init__(self, cap_usd: float = DEFAULT_CAP_USD, path=LEDGER_FILE) -> None:
        self.cap = cap_usd
        self.path = path
        self._lock = threading.Lock()
        self._spent = sum(float(r.get("cost_usd") or 0.0) for r in read_jsonl(path))
        self._reserved = 0.0

    @property
    def spent(self) -> float:
        return self._spent

    def reserve(self, amount: float) -> None:
        """Refuse a call whose worst case would take the total over the cap."""
        with self._lock:
            if self._spent + self._reserved + amount > self.cap:
                raise LabError(f"Budget cap: spent ${self._spent:.2f} of ${self.cap:.2f}; the next call could cost up to ${amount:.2f}. Stopping before the cap is exceeded.")
            self._reserved += amount

    def settle(self, reserved: float, row: dict) -> None:
        with self._lock:
            self._reserved = max(0.0, self._reserved - reserved)
            cost = float(row.get("cost_usd") or 0.0)
            self._spent += cost
            append_jsonl(self.path, {"at": now_iso(), **row})
