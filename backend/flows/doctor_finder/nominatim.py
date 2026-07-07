"""Nominatim (OpenStreetMap) geocoder — free country resolver, SECONDARY to ROR.

Used only when ROR cannot confidently resolve an affiliation, and BEFORE the paid Brave+LLM
fallback. OpenStreetMap's usage policy is strict: at most 1 request/second and a valid identifying
User-Agent. The caller therefore runs this sequentially with a >=1s spacing and a hard per-run cap;
this module just performs one polite lookup and returns an ISO country only on a clean hit.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_TIMEOUT_SEC = 12.0
NOMINATIM_USER_AGENT = "GeneQuestGeneGuidelines/1.0 (+https://genequest.org; mailto:info@genequest.org)"


@dataclass(frozen=True)
class NominatimMatch:
    country_code: str
    city: str = ""


def _country_from_results(data: object) -> NominatimMatch | None:
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict):
        return None
    addr = first.get("address") or {}
    if not isinstance(addr, dict):
        return None
    code = str(addr.get("country_code") or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return None
    city = str(addr.get("city") or addr.get("town") or addr.get("village") or "").strip()
    return NominatimMatch(country_code=code, city=city)


async def lookup_affiliation_country(
    affiliation: str,
    *,
    institution: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> NominatimMatch | None:
    """Geocode an affiliation/institution to a country via Nominatim, or None if no clean hit.

    Prefers the (cleaner) institution name when available, else the raw affiliation string. Returns
    None on any network error or a result without an ISO country code (better empty than wrong).
    """
    query = (institution or "").strip() or (affiliation or "").strip()
    if not query:
        return None
    params = {
        "q": query[:300],
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": "1",
    }
    headers = {"User-Agent": NOMINATIM_USER_AGENT, "Accept-Language": "en"}

    async def _do(c: httpx.AsyncClient) -> NominatimMatch | None:
        try:
            resp = await c.get(NOMINATIM_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001 - any failure => no assignment (safe)
            log.debug("nominatim lookup failed for %r: %s", query[:80], exc)
            return None
        return _country_from_results(data)

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=NOMINATIM_TIMEOUT_SEC) as c:
        return await _do(c)
