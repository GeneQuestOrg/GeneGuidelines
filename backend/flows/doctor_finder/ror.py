"""ROR (Research Organization Registry) client — free, no-auth institution → country resolver.

Primary resolver for the doctor_finder geo step (df-20): when PubMed gives an affiliation without a
parseable country, ROR's affiliation-matching endpoint maps the institution string to a canonical
research organization that already carries a verified ISO country. It is free and needs no key, so
it runs BEFORE the paid Brave+LLM fallback.

Conservative by design (same philosophy as ``nppes.py``): we trust ONLY a match ROR itself flags
``chosen: true`` and that carries a 2-letter ISO country. Otherwise we return None — ROR happily
returns an unrelated same-name org in another country with ``chosen: false`` (e.g. a "Children's
Hospital" in Tunisia, or a Malaysian org for an "NIH branch" string), which would recreate the very
MD→Moldova class of bug this step exists to prevent.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

ROR_API_URL = "https://api.ror.org/v2/organizations"
ROR_TIMEOUT_SEC = 12.0
# ROR asks heavier users to identify themselves with a User-Agent / mailto.
ROR_USER_AGENT = "GeneQuestGeneGuidelines/1.0 (+https://genequest.org; mailto:info@genequest.org)"


@dataclass(frozen=True)
class RorMatch:
    country_code: str
    country_name: str = ""
    city: str = ""
    ror_id: str = ""
    score: float = 0.0


def _country_from_item(item: dict) -> RorMatch | None:
    org = item.get("organization") or {}
    if not isinstance(org, dict):
        return None
    locs = org.get("locations") or []
    geo: dict = {}
    if isinstance(locs, list) and locs and isinstance(locs[0], dict):
        geo = locs[0].get("geonames_details") or {}
    code = str(geo.get("country_code") or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return None
    return RorMatch(
        country_code=code,
        country_name=str(geo.get("country_name") or "").strip(),
        city=str(geo.get("name") or "").strip(),
        ror_id=str(org.get("id") or "").strip(),
        score=float(item.get("score") or 0.0),
    )


def _pick_chosen(items: object, *, min_score: float) -> RorMatch | None:
    """Return the country for the single item ROR marked ``chosen`` (if it clears min_score)."""
    if not isinstance(items, list):
        return None
    for it in items:
        if not isinstance(it, dict) or it.get("chosen") is not True:
            continue
        if float(it.get("score") or 0.0) < min_score:
            return None  # ROR chose it but with low confidence — refuse rather than risk a wrong country
        return _country_from_item(it)
    return None


async def lookup_affiliation_country(
    affiliation: str,
    *,
    min_score: float = 0.9,
    client: httpx.AsyncClient | None = None,
) -> RorMatch | None:
    """Resolve an affiliation string to a confident ISO country via ROR, or None if unsure.

    Returns None on any network error, empty result, or a non-``chosen`` / low-score match. The
    caller then falls through to the next (Nominatim → Brave) resolver or leaves the country unset.
    """
    aff = (affiliation or "").strip()
    if not aff:
        return None
    params = {"affiliation": aff[:2000]}
    headers = {"User-Agent": ROR_USER_AGENT}

    async def _do(c: httpx.AsyncClient) -> RorMatch | None:
        try:
            resp = await c.get(ROR_API_URL, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001 - any failure => no assignment (safe)
            log.debug("ror lookup failed for %r: %s", aff[:80], exc)
            return None
        items = data.get("items") if isinstance(data, dict) else None
        return _pick_chosen(items, min_score=min_score)

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=ROR_TIMEOUT_SEC) as c:
        return await _do(c)
