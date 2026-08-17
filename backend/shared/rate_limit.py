"""A small per-client sliding-window limiter for anonymous public endpoints.

Third copy of this logic in the tree (``routers/geo.py``, ``routers/feedback.py``),
so it lives here now. Deliberately in-process and in-memory: production runs a
single replica, and a Redis dependency to slow down anonymous abuse of a non-profit
site would cost more than it protects. It does not survive a restart and does not
coordinate across replicas — if the app ever scales out, this becomes per-replica
and needs replacing rather than tuning.

**Client identity.** ``request.client.host`` is the wrong thing to key on here.
Uvicorn runs without ``--proxy-headers`` behind the Azure Container Apps ingress, so
every request from the internet arrives with the ingress address as its peer (they
show up in the logs as ``100.100.x.x``). Keying on that turns a per-IP limit into a
single global limit, where one abusive caller locks out every visitor. So we read the
left-most entry of ``X-Forwarded-For``, which the ingress sets, and fall back to the
peer address only when the header is absent (local dev, direct calls).

X-Forwarded-For is client-supplied and can be spoofed. That is acceptable for what
this defends — accidental hammering and casual abuse of endpoints that each cost one
LLM call — and it is strictly better than the global bucket it replaces. Anything
that needs to survive a determined attacker needs an edge rate limit, not this.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request

_buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))


def client_key(request: Request) -> str:
    """Best available identity for the caller (see the module docstring)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def check_rate_limit(
    request: Request,
    *,
    bucket: str,
    max_calls: int,
    window_sec: float,
    detail: str = "Too many requests — please try again in a little while.",
) -> None:
    """Raise 429 when this caller exceeded ``max_calls`` within ``window_sec``.

    ``bucket`` namespaces the counter so one endpoint's traffic cannot exhaust
    another's allowance.
    """
    key = client_key(request)
    now = time.monotonic()
    window_start = now - window_sec
    stamps = _buckets[bucket][key]
    stamps[:] = [t for t in stamps if t > window_start]
    if len(stamps) >= max_calls:
        raise HTTPException(status_code=429, detail=detail)
    stamps.append(now)


def reset_for_tests() -> None:
    """Drop all counters — tests share a process."""
    _buckets.clear()


__all__ = ["check_rate_limit", "client_key", "reset_for_tests"]
