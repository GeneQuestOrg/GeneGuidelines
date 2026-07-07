"""Doctor Finder stage: attach a canonical clinical specialty + real practice location.

Phase 1 scope: US physicians via NPPES (free, authoritative, returns a NUCC code + LOCATION
address). Non-US authors are left without a verified specialty for now (Phase 2/3 add NIL + clinic
LLM extraction). Discovery (who knows the disease) is unchanged — this only ADDS the clinical axis.

Design:
- runs over ``aggregated_authors`` (name + country + affiliation already resolved);
- only queries NPPES for US authors; conservative identity matching in ``nppes.py`` means we
  attach a specialty ONLY when one plausible physician is identified, else leave it unverified;
- deterministic Tier-1 taxonomy match maps the returned NUCC code straight to a canonical entry;
- concurrency-bounded + cached, mirroring ``affiliation_georesolve``.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

try:
    from ...config import (
        DOCTOR_FINDER_SPECIALTY_CONCURRENCY,
        DOCTOR_FINDER_SPECIALTY_MAX_LOOKUPS,
    )
    from . import nppes, specialty_taxonomy
except ImportError:  # pragma: no cover - flat-layout import shim
    from config import (  # type: ignore[no-redef]
        DOCTOR_FINDER_SPECIALTY_CONCURRENCY,
        DOCTOR_FINDER_SPECIALTY_MAX_LOOKUPS,
    )
    import nppes  # type: ignore[no-redef]
    import specialty_taxonomy  # type: ignore[no-redef]

log = logging.getLogger(__name__)

_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC",
}
# ", MD" / ", MD 20892" / ", Bethesda, MD" — capture a 2-letter USPS state token in an affiliation.
_STATE_RE = re.compile(r",\s*([A-Z]{2})\b(?:\s+\d{5})?")

_CACHE: dict[str, dict[str, Any] | None] = {}
_CACHE_MAX = 4000
_DOCTOR_FINDER_PROGRESS_KIND = "doctor_finder_progress"


def _us_state_from_author(author: dict[str, Any]) -> str:
    """Best-effort 2-letter US state from the author's affiliations (helps NPPES precision)."""
    haystacks: list[str] = []
    inst = author.get("institution_primary")
    if inst:
        haystacks.append(str(inst))
    for p in author.get("papers") or []:
        pa = p.get("parsed_affiliation") if isinstance(p, dict) else None
        if isinstance(pa, dict):
            for key in ("raw", "city"):
                v = pa.get(key)
                if v:
                    haystacks.append(str(v))
        for raw in (p.get("affiliations_raw") or []) if isinstance(p, dict) else []:
            if raw:
                haystacks.append(str(raw))
    for text in haystacks:
        for m in _STATE_RE.finditer(text):
            tok = m.group(1).upper()
            if tok in _US_STATES:
                return tok
    return ""


def _cache_put(key: str, value: dict[str, Any] | None) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        for _ in range(_CACHE_MAX // 2):
            if not _CACHE:
                break
            _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = value


def _specialty_from_match(match: nppes.NppesMatch) -> dict[str, Any] | None:
    """Map an NPPES match to a canonical ClinicalSpecialty dict (+ practice), or None."""
    entry = specialty_taxonomy.entry_for_code(match.taxonomy_code)
    # Prefer our canonical label; fall back to NPPES desc if the code is unknown to our table.
    label = entry.label_en if entry else (match.taxonomy_desc or "")
    if not label:
        return None
    group = entry.classification if entry else ""
    practice: dict[str, Any] | None = None
    if match.city or match.address_1:
        practice = {
            "type": "primary",
            "name": match.org_name or "Practice location (NPPES)",
            "address": match.address_1 or None,
            "city": match.city or "—",
            "state": match.state or "",
            "country": "US",
            "source": "nppes",
            "confidence": match.confidence,
        }
    return {
        "specialty": {
            "canonicalCode": match.taxonomy_code,
            "labelEn": label,
            "group": group,
            "source": "nppes",
            "confidence": match.confidence,
        },
        "practice": practice,
        "npi": match.npi,
    }


async def _resolve_one(
    author: dict[str, Any], *, client: httpx.AsyncClient
) -> dict[str, Any] | None:
    last = str(author.get("last_name") or "").strip()
    fore = str(author.get("fore_name") or "").strip()
    country = str(author.get("country_primary") or "").strip().upper()
    if country != "US" or not last:
        return None
    state = _us_state_from_author(author)
    cache_key = f"{last.lower()}|{fore[:1].lower()}|{state}"
    if cache_key in _CACHE:
        hit = _CACHE[cache_key]
        return dict(hit) if hit else None
    match = await nppes.lookup_us_specialty(
        last_name=last, first_name=fore, state=state, client=client
    )
    result = _specialty_from_match(match) if match else None
    _cache_put(cache_key, result)
    return dict(result) if result else None


def _emit_progress(context: dict[str, Any], *, done: int, total: int) -> None:
    tup = context.get("_doctor_finder_emit")
    if not isinstance(tup, tuple) or len(tup) != 2:
        return
    emit_fn, eq = tup[0], tup[1]
    if not emit_fn or not eq:
        return
    emit_fn(eq, {
        "kind": _DOCTOR_FINDER_PROGRESS_KIND,
        "stage": "specialty_enrich",
        "done": done,
        "total": total,
    })


async def run_async(context: dict[str, Any]) -> dict[str, Any]:
    """Attach ``clinical_specialties``/``reachability``/``resolved_practice`` to US authors.

    No-op (returns context unchanged) when the NUCC taxonomy file is absent, so a fresh checkout
    without the data asset still runs the finder end to end.
    """
    authors = list(context.get("aggregated_authors") or [])
    if not authors:
        return context
    if not specialty_taxonomy.is_loaded():
        log.info("specialty_enrich: NUCC taxonomy not loaded; skipping specialty step")
        return context

    us_indices = [
        i for i, a in enumerate(authors)
        if str(a.get("country_primary") or "").upper() == "US" and a.get("last_name")
    ]
    # Busiest authors first so the lookup budget helps the most-visible rows.
    us_indices.sort(key=lambda i: int(authors[i].get("paper_count") or 0), reverse=True)
    us_indices = us_indices[:DOCTOR_FINDER_SPECIALTY_MAX_LOOKUPS]
    total = len(us_indices)
    if total == 0:
        return context

    log.info("specialty_enrich: NPPES lookup for %d US author(s)", total)
    sem = asyncio.Semaphore(DOCTOR_FINDER_SPECIALTY_CONCURRENCY)
    enriched: dict[int, dict[str, Any]] = {}
    done = 0

    async with httpx.AsyncClient(timeout=nppes.NPPES_TIMEOUT_SEC) as client:
        async def _bounded(idx: int) -> None:
            nonlocal done
            async with sem:
                try:
                    res = await _resolve_one(authors[idx], client=client)
                    if res:
                        enriched[idx] = res
                finally:
                    done += 1
                    if done % 10 == 0 or done == total:
                        _emit_progress(context, done=done, total=total)

        await asyncio.gather(*(_bounded(i) for i in us_indices))

    matched = 0
    out_authors: list[dict[str, Any]] = []
    for i, author in enumerate(authors):
        res = enriched.get(i)
        if not res:
            out_authors.append(author)
            continue
        matched += 1
        au = dict(author)
        au["clinical_specialties"] = [res["specialty"]]
        # NPPES lists an individual physician with a practice address => they see patients.
        au["reachability"] = "sees_patients"
        if res.get("practice"):
            au["resolved_practice"] = res["practice"]
        if res.get("npi"):
            au["npi"] = res["npi"]
        out_authors.append(au)

    log.info("specialty_enrich: matched %d/%d US authors to a NUCC specialty", matched, total)
    return {**context, "aggregated_authors": out_authors}
