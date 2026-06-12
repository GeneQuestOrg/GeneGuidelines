"""Geo search proxy — forwards free-text queries to Nominatim/OSM."""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["geo"])

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_CONTACT_EMAIL = os.environ.get("NOMINATIM_CONTACT_EMAIL", "api@geneguidelines.org")
_USER_AGENT = f"GeneGuidelines/1.0 ({_CONTACT_EMAIL})"

# Simple in-process rate limiter: max 2 requests per IP per second (well within
# Nominatim's 1 req/s policy; the debounce on the frontend reduces real traffic).
_RATE_WINDOW = 1.0
_RATE_MAX = 2
_ip_timestamps: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    window_start = now - _RATE_WINDOW
    ts = _ip_timestamps[ip]
    ts[:] = [t for t in ts if t > window_start]
    if len(ts) >= _RATE_MAX:
        raise HTTPException(status_code=429, detail="Too many requests")
    ts.append(now)


class GeoResult(BaseModel):
    lat: float
    lng: float
    displayName: str


@router.get("/geo/search", response_model=list[GeoResult])
async def geo_search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=200),
) -> list[GeoResult]:
    """Return up to 5 geocoded candidates for a free-text location query."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                _NOMINATIM_URL,
                params={"q": q, "format": "json", "limit": 5, "addressdetails": 0},
                headers={"User-Agent": _USER_AGENT},
            )
            resp.raise_for_status()
            rows: list[dict] = resp.json()
            return [
                GeoResult(lat=float(r["lat"]), lng=float(r["lon"]), displayName=r["display_name"])
                for r in rows
            ]
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Geocoding service timed out")
    except httpx.HTTPError:
        logger.warning("Nominatim HTTP error for query %r", q)
        raise HTTPException(status_code=502, detail="Geocoding service unavailable")
    except Exception:
        logger.exception("Unexpected geocoding error for query %r", q)
        raise HTTPException(status_code=502, detail="Geocoding failed")
