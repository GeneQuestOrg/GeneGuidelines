"""Geo search proxy — forwards free-text queries to Nominatim/OSM."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(tags=["geo"])

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "GeneGuidelines/1.0 (maciej@genequest.org)"


class GeoResult(BaseModel):
    lat: float
    lng: float
    displayName: str


@router.get("/geo/search", response_model=list[GeoResult])
async def geo_search(q: str = Query(..., min_length=2, max_length=200)) -> list[GeoResult]:
    """Return up to 5 geocoded candidates for a free-text location query."""
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
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Nominatim timeout")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Nominatim error: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Geocoding parse error: {exc}")
