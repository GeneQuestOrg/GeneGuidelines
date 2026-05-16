"""Brave Web Search API client for affiliation geolocation (Doctor Finder)."""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_SEARCH_TIMEOUT_SEC = 15.0
BRAVE_MAX_RESULTS = 8


async def brave_web_search(
    query: str,
    *,
    api_key: str,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, str]]:
    """Return up to ``BRAVE_MAX_RESULTS`` web hits with title, url, description (empty if API fails).

    Args:
        query: Search query string.
        api_key: Brave ``X-Subscription-Token`` (from ``BRAVE_API_KEY`` env).
        client: Optional shared async client.

    Returns:
        List of dicts with keys title, url, description (strings; may be empty).
    """
    q = (query or "").strip()
    if not q or not (api_key or "").strip():
        return []

    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key.strip(),
    }
    params = {"q": q, "count": str(min(BRAVE_MAX_RESULTS, 20))}

    async def _do(c: httpx.AsyncClient) -> list[dict[str, str]]:
        try:
            resp = await c.get(BRAVE_WEB_SEARCH_URL, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.warning("brave_web_search: request failed: %s", exc)
            return []
        web = data.get("web") if isinstance(data, dict) else None
        results = web.get("results") if isinstance(web, dict) else None
        if not isinstance(results, list):
            return []
        out: list[dict[str, str]] = []
        for item in results[:BRAVE_MAX_RESULTS]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            desc = str(item.get("description") or item.get("snippet") or "").strip()
            out.append({"title": title, "url": url, "description": desc})
        return out

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=BRAVE_SEARCH_TIMEOUT_SEC) as c:
        return await _do(c)


def format_brave_hits_for_llm(hits: list[dict[str, Any]]) -> str:
    """Turn Brave hit dicts into a compact numbered block for the LLM."""
    lines: list[str] = []
    for i, h in enumerate(hits, start=1):
        title = str(h.get("title") or "")
        url = str(h.get("url") or "")
        desc = str(h.get("description") or "")
        lines.append(f"{i}. {title}\n   URL: {url}\n   Snippet: {desc[:500]}")
    return "\n\n".join(lines) if lines else "(no web results)"
