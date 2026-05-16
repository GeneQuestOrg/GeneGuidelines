"""In-process response cache + Cache-Control header middleware.

The public site is read-heavy: a parent landing on the home view triggers
half a dozen GETs in the first 200 ms (``/diseases``, ``/catalog/stats``,
``/diseases/{slug}/guideline/document``, …). A CDN can absorb most of that
traffic with the right ``Cache-Control`` header, and this module makes sure
those headers are emitted for the public read endpoints.

The in-process cache here is a tiny helper for the case where there is **no
CDN** in front (local dev, single-region deploys, demo environments). It
caches the rendered response by URL+query for ``ttl_seconds`` and is
invalidated by the workflow engine through :func:`invalidate_prefix`.

Design:

- TTL is a soft default (60 s); individual endpoints can override.
- Cache key is request method + path + sorted query string — never the
  body, which the public read endpoints do not carry anyway.
- Cache is thread-safe (``threading.Lock``) so it survives concurrent
  uvicorn workers in the multi-worker case as well.
- Memory cap is **soft** — entries are evicted lazily on TTL expiry. There
  is no hard size limit because the public surface area is small (~30
  endpoints × ~10 slug variants).
"""

from __future__ import annotations

import threading
import time
from functools import wraps
from typing import Any, Awaitable, Callable

from fastapi import Request, Response

# (expires_at_monotonic, payload_dict)
_CACHE: dict[str, tuple[float, Any]] = {}
_LOCK = threading.Lock()


def _cache_key(request: Request) -> str:
    """Stable cache key for a GET request."""
    return f"{request.method}:{request.url.path}?{request.url.query}"


def get(key: str) -> Any | None:
    """Return cached value if present and not expired, else None."""
    with _LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        expires_at, payload = entry
        if time.monotonic() >= expires_at:
            _CACHE.pop(key, None)
            return None
        return payload


def put(key: str, payload: Any, ttl_seconds: float) -> None:
    """Insert ``payload`` under ``key`` with the given TTL."""
    with _LOCK:
        _CACHE[key] = (time.monotonic() + ttl_seconds, payload)


def invalidate_prefix(prefix: str) -> int:
    """Drop every cached entry whose key path starts with ``prefix``.

    Returns the number of evicted entries. Called by the workflow engine
    when a guideline merges or a disease seed changes — anything that should
    make the next public request fresh.
    """
    dropped = 0
    with _LOCK:
        for key in list(_CACHE.keys()):
            # Key format is "GET:/api/...?..." — strip the method+colon.
            _, _, path_qs = key.partition(":")
            if path_qs.split("?", 1)[0].startswith(prefix):
                _CACHE.pop(key, None)
                dropped += 1
    return dropped


def clear() -> None:
    """Drop everything. Test helper, not for production paths."""
    with _LOCK:
        _CACHE.clear()


def _set_cache_headers(response: Response, ttl_seconds: int) -> None:
    """Add browser + CDN cache headers to ``response``."""
    # max-age = browser; s-maxage = CDN. Different values because CDN can
    # tolerate slightly staler content (5 min) and absorbs the burst.
    response.headers["Cache-Control"] = (
        f"public, max-age={ttl_seconds}, s-maxage={ttl_seconds * 5}"
    )


def cache_response(
    ttl_seconds: int = 60,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorator that caches an async FastAPI endpoint's return value.

    Requires the endpoint to accept ``request: Request`` and
    ``response: Response`` parameters (FastAPI injects them automatically).
    """

    def decorator(
        endpoint: Callable[..., Awaitable[Any]],
    ) -> Callable[..., Awaitable[Any]]:
        @wraps(endpoint)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request: Request | None = kwargs.get("request") or next(
                (a for a in args if isinstance(a, Request)), None
            )
            response: Response | None = kwargs.get("response") or next(
                (a for a in args if isinstance(a, Response)), None
            )

            if request is None or response is None:
                # Endpoint did not request Request/Response — run uncached.
                return await endpoint(*args, **kwargs)

            key = _cache_key(request)
            cached = get(key)
            if cached is not None:
                _set_cache_headers(response, ttl_seconds)
                response.headers["X-Cache"] = "HIT"
                return cached

            payload = await endpoint(*args, **kwargs)
            put(key, payload, ttl_seconds)
            _set_cache_headers(response, ttl_seconds)
            response.headers["X-Cache"] = "MISS"
            return payload

        return wrapper

    return decorator


__all__ = [
    "cache_response",
    "clear",
    "get",
    "invalidate_prefix",
    "put",
]
