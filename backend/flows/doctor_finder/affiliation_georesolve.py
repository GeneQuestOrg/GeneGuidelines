"""Infer country/continent for PubMed affiliations missing ISO2, cheapest source first.

Resolver chain (df-20), each stage only sees what the previous could not resolve:
ROR (free registry) → Nominatim (free OSM geocoder, 1 req/s) → Brave web search + LLM (paid, last resort).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections import Counter
from typing import Any, Callable

import httpx
import pycountry
from pydantic import BaseModel, Field, field_validator

from ...agents.simple_runner import resolve_max_tokens_for_node, resolve_model_spec_for_node, run_llm_simple_async
from ...config import (
    DOCTOR_FINDER_GEO_BRAVE_CONCURRENCY,
    DOCTOR_FINDER_GEO_CONFIDENCE_MIN,
    DOCTOR_FINDER_GEO_MAX_AFFILIATIONS,
    DOCTOR_FINDER_GEO_MIN_AFF_CHARS,
)
from .affiliation_parser import parse_affiliation
from .brave_search import brave_web_search, format_brave_hits_for_llm
from .country_continent_table import continent_for_iso_alpha2

log = logging.getLogger(__name__)

_GEO_RESULT_CACHE: dict[str, dict[str, Any] | None] = {}
_GEO_CACHE_MAX = 4000

_DOCTOR_FINDER_PROGRESS_KIND = "doctor_finder_progress"


def _brave_api_key() -> str | None:
    """Read Brave token at call time so tests can patch ``backend.config.BRAVE_API_KEY``."""
    from ...config import BRAVE_API_KEY as key

    return (key or "").strip() or None


_GEO_SYSTEM = (
    "You infer the PRIMARY country of a medical institution or affiliation string using ONLY the "
    "numbered web search snippets below. Rules:\n"
    "- If snippets clearly agree on one country, return its ISO 3166-1 alpha-2 code and high confidence.\n"
    "- If snippets conflict, are irrelevant, or do not support a country, return country_iso2=null "
    "and low confidence.\n"
    "- Do not use private geographic knowledge when snippets are empty or unhelpful.\n"
    "- Rationale must cite snippet numbers (e.g. \"1+3\") in one short sentence."
)


class GeoResolveLLMOut(BaseModel):
    """Structured LLM output for affiliation → ISO-2."""

    country_iso2: str | None = Field(default=None, max_length=2)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    rationale: str = Field(default="", max_length=500)

    @field_validator("country_iso2", mode="before")
    @classmethod
    def _iso2(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        s = str(v).strip().upper()
        if len(s) != 2 or not s.isalpha():
            return None
        if pycountry.countries.get(alpha_2=s) is None:
            return None
        return s


def _cache_key(raw: str) -> str:
    norm = " ".join(raw.strip().lower().split())[:2000]
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _brave_query(raw: str, institution: str | None) -> str:
    focus = (institution or "").strip() or raw.strip()
    focus = " ".join(focus.split())[:200]
    return f"{focus} medical school hospital country headquarters location"


def _emit_geo_progress(context: dict[str, Any], *, done: int, total: int) -> None:
    tup = context.get("_doctor_finder_emit")
    if not tup or len(tup) != 2:
        return
    emit_fn, eq = tup[0], tup[1]
    if not emit_fn or not eq:
        return
    emit_fn(
        eq,
        {
            "kind": _DOCTOR_FINDER_PROGRESS_KIND,
            "stage": "affiliation_georesolve",
            "done": done,
            "total": total,
        },
    )


def _model_spec(context: dict[str, Any]) -> str:
    initial = context.get("initial") or {}
    raw = str(initial.get("llm_model_override") or "").strip()
    if raw:
        return raw if ":" in raw else f"openai:{raw}"
    return resolve_model_spec_for_node({"prompt_mode": "simple", "model_name": ""})


def _collect_tasks(articles: list[dict[str, Any]]) -> list[tuple[str, str, str | None]]:
    """Unique (cache_key, raw affiliation, institution) rows needing country_code.

    PubMed often puts the country on a different ``affiliations_raw`` line than the
    parser's chosen ``parsed_affiliation.raw`` (first line without any resolved country).
    We collect every unresolved line per author, count global frequency, and process
    the most common keys first so the Brave+LLM budget helps the widest coverage.
    """
    key_freq: Counter[str] = Counter()
    key_to_raw: dict[str, str] = {}
    key_to_inst: dict[str, str | None] = {}

    for article in articles:
        for author in article.get("authors") or []:
            pa = author.get("parsed_affiliation")
            if isinstance(pa, dict) and pa.get("country_code"):
                continue
            seen_author: set[str] = set()
            raws: list[str] = []
            for aff in author.get("affiliations_raw") or []:
                s = str(aff).strip()
                if s and s not in seen_author:
                    seen_author.add(s)
                    raws.append(s)
            if isinstance(pa, dict):
                pr = str(pa.get("raw") or "").strip()
                if pr and pr not in seen_author:
                    raws.append(pr)

            for raw in raws:
                if len(raw) < DOCTOR_FINDER_GEO_MIN_AFF_CHARS:
                    continue
                cand = parse_affiliation(raw)
                if cand.country_code:
                    continue
                key = _cache_key(raw)
                key_freq[key] += 1
                if key not in key_to_raw:
                    key_to_raw[key] = raw
                    inst = cand.institution
                    key_to_inst[key] = str(inst).strip() if inst else None

    ordered = key_freq.most_common(DOCTOR_FINDER_GEO_MAX_AFFILIATIONS)
    return [(k, key_to_raw[k], key_to_inst.get(k)) for k, _ in ordered]


def _cache_put(key: str, value: dict[str, Any] | None) -> None:
    if len(_GEO_RESULT_CACHE) >= _GEO_CACHE_MAX:
        for _ in range(_GEO_CACHE_MAX // 2):
            if not _GEO_RESULT_CACHE:
                break
            _GEO_RESULT_CACHE.pop(next(iter(_GEO_RESULT_CACHE)))
    _GEO_RESULT_CACHE[key] = value


def _patch_from_iso2(iso2: str, confidence: float, source: str = "brave_web_llm") -> dict[str, Any]:
    c = pycountry.countries.get(alpha_2=iso2)
    name = c.name if c else iso2
    cont = continent_for_iso_alpha2(iso2)
    return {
        "country_code": iso2,
        "country_name": name,
        "continent": cont,
        "geo_source": source,
        "geo_confidence": round(float(confidence), 3),
    }


async def _resolve_one(
    key: str,
    raw: str,
    institution: str | None,
    *,
    api_key: str,
    model_spec: str,
    store: dict[str, Any],
    emit_fn: Callable[..., Any],
    event_queue: Any,
    http_client: httpx.AsyncClient,
) -> dict[str, Any] | None:
    if key in _GEO_RESULT_CACHE:
        hit = _GEO_RESULT_CACHE[key]
        return dict(hit) if hit else None

    query = _brave_query(raw, institution)
    hits = await brave_web_search(query, api_key=api_key, client=http_client)
    # No web evidence (genuinely no results, or a 429 on Brave's 1 req/s free tier) => do NOT call
    # the LLM. Without snippets it can only guess from the raw string ROR already failed on, which
    # reliably yields a below-threshold (rejected) answer AND triggers max_retry schema retries — a
    # storm that dominated df-20 runtime. Skipping keeps Brave evidence-based and the stage fast.
    if not hits:
        _cache_put(key, None)
        return None
    block = format_brave_hits_for_llm(hits)
    user_prompt = (
        f"Affiliation string from PubMed:\n{raw[:1200]}\n\n"
        f"Institution field (may be empty):\n{institution or '(none)'}\n\n"
        f"--- Web search snippets ---\n{block}\n\n"
        "Return country_iso2, confidence, rationale per schema."
    )
    max_tokens = resolve_max_tokens_for_node({"prompt_mode": "simple", "max_tokens": 400})
    raw_out = await run_llm_simple_async(
        system_prompt=_GEO_SYSTEM,
        user_prompt=user_prompt,
        result_type=GeoResolveLLMOut,
        model_spec=model_spec,
        max_tokens=max_tokens,
        max_retry=2,
        store=store,
        event_queue=event_queue,
        node_id="doctor_finder:affiliation_georesolve",
        emit_fn=emit_fn,
        poison_store_on_failure=False,
        sse_kind="llm_simple",
    )
    if not raw_out:
        _cache_put(key, None)
        return None
    iso = raw_out.get("country_iso2")
    conf = float(raw_out.get("confidence") or 0.0)
    if not isinstance(iso, str) or conf < DOCTOR_FINDER_GEO_CONFIDENCE_MIN:
        _cache_put(key, None)
        return None
    patch = _patch_from_iso2(iso, conf)
    _cache_put(key, patch)
    return patch


def _rebuild_parsed_affiliation(author: dict[str, Any], patches: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the first affiliation line (XML order) that has ``country_code`` after parser + patches."""
    affs = author.get("affiliations_raw") or []
    if isinstance(affs, list) and affs:
        for aff in affs:
            s = str(aff).strip()
            if not s:
                continue
            base = parse_affiliation(s).model_dump()
            pk = _cache_key(s)
            if pk in patches:
                base = {**base, **patches[pk]}
            if base.get("country_code"):
                return base
    pa = author.get("parsed_affiliation")
    if not isinstance(pa, dict):
        return None
    raw = str(pa.get("raw") or "").strip()
    if raw:
        pk = _cache_key(raw)
        if pk in patches:
            merged = {**pa, **patches[pk]}
            if merged.get("country_code"):
                return merged
    return pa


def _apply_patches(articles: list[dict[str, Any]], patches: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for article in articles:
        authors_out: list[dict[str, Any]] = []
        for author in article.get("authors") or []:
            au = dict(author)
            rebuilt = _rebuild_parsed_affiliation(author, patches)
            if rebuilt is not None:
                au["parsed_affiliation"] = rebuilt
            authors_out.append(au)
        out.append({**article, "authors": authors_out})
    return out


async def _run_ror_stage(
    remaining: list[tuple[str, str, str | None]],
    patches: dict[str, dict[str, Any]],
    *,
    concurrency: int,
    min_score: float,
) -> list[tuple[str, str, str | None]]:
    """Fill countries from ROR (free, no key). Returns the tasks ROR could not confidently resolve."""
    from . import ror

    results: dict[str, Any] = {}
    sem = asyncio.Semaphore(max(1, concurrency))

    async with httpx.AsyncClient(timeout=ror.ROR_TIMEOUT_SEC) as client:

        async def _one(t: tuple[str, str, str | None]) -> None:
            key, raw, _inst = t
            async with sem:
                try:
                    results[key] = await ror.lookup_affiliation_country(raw, min_score=min_score, client=client)
                except Exception:  # noqa: BLE001 - a resolver must never fail the whole run
                    results[key] = None

        await asyncio.gather(*(_one(t) for t in remaining))

    still: list[tuple[str, str, str | None]] = []
    for t in remaining:
        m = results.get(t[0])
        if m and getattr(m, "country_code", None):
            patch = _patch_from_iso2(m.country_code, min(1.0, m.score or 0.95), source="ror")
            patches[t[0]] = patch
            _cache_put(t[0], patch)
        else:
            still.append(t)
    return still


async def _run_nominatim_stage(
    remaining: list[tuple[str, str, str | None]],
    patches: dict[str, dict[str, Any]],
    *,
    max_lookups: int,
    min_interval_sec: float,
) -> list[tuple[str, str, str | None]]:
    """Fill countries from Nominatim (free). Sequential + bounded per OSM's 1 req/s fair-use policy."""
    from . import nominatim

    if max_lookups <= 0:
        return list(remaining)

    still: list[tuple[str, str, str | None]] = []
    used = 0
    async with httpx.AsyncClient(timeout=nominatim.NOMINATIM_TIMEOUT_SEC) as client:
        for t in remaining:
            key, raw, inst = t
            if used >= max_lookups:
                still.append(t)
                continue
            if used > 0:
                await asyncio.sleep(min_interval_sec)  # OSM fair-use: keep <=1 req/s
            try:
                m = await nominatim.lookup_affiliation_country(raw, institution=inst, client=client)
            except Exception:  # noqa: BLE001
                m = None
            used += 1
            if m and m.country_code:
                patch = _patch_from_iso2(m.country_code, 0.75, source="nominatim")
                patches[key] = patch
                _cache_put(key, patch)
            else:
                still.append(t)
    return still


async def _run_brave_stage(
    remaining: list[tuple[str, str, str | None]],
    patches: dict[str, dict[str, Any]],
    *,
    api_key: str,
    context: dict[str, Any],
    emit_fn: Callable[..., Any],
    event_queue: Any,
    max_lookups: int,
) -> list[tuple[str, str, str | None]]:
    """Last resort: Brave web search + LLM. Reached only for what ROR/Nominatim left unresolved.

    ``max_lookups`` caps the PAID stage independently of how many affiliations entered the pipeline:
    only the first (most frequent) ``max_lookups`` unresolved affiliations are searched; the rest
    stay unresolved. Keeps spend bounded regardless of DOCTOR_FINDER_GEO_MAX_AFFILIATIONS.
    """
    if max_lookups <= 0:
        return remaining
    to_process = remaining[:max_lookups]
    overflow = remaining[max_lookups:]
    if overflow:
        log.info(
            "affiliation_georesolve: brave capped at %d lookup(s); %d affiliation(s) left unresolved",
            max_lookups,
            len(overflow),
        )
    model_spec = _model_spec(context)
    store: dict[str, Any] = {}
    sem = asyncio.Semaphore(DOCTOR_FINDER_GEO_BRAVE_CONCURRENCY)
    results: dict[str, Any] = {}

    async def _bounded(t: tuple[str, str, str | None]) -> None:
        key, raw, inst = t
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    results[key] = await _resolve_one(
                        key,
                        raw,
                        inst,
                        api_key=api_key,
                        model_spec=model_spec,
                        store=store,
                        emit_fn=emit_fn,
                        event_queue=event_queue,
                        http_client=client,
                    )
            except Exception:  # noqa: BLE001
                results[key] = None

    await asyncio.gather(*(_bounded(t) for t in to_process))

    still: list[tuple[str, str, str | None]] = list(overflow)
    for t in to_process:
        p = results.get(t[0])
        if p:
            patches[t[0]] = p
        else:
            still.append(t)
    return still


async def run_async(context: dict[str, Any]) -> dict[str, Any]:
    """Enrich affiliations missing an ISO country, cheapest source first.

    Staged resolver chain — each stage only sees affiliations the previous one could not resolve:
      1. ROR — free, no key, canonical institution registry with a verified ISO country (PRIMARY).
      2. Nominatim — free OpenStreetMap geocoder, 1 req/s, bounded per run (SECONDARY).
      3. Brave web search + LLM — paid, LAST resort; runs only when ``BRAVE_API_KEY`` is set.
    """
    articles = list(context.get("articles") or [])
    if not articles:
        return context

    from ...config import (
        DOCTOR_FINDER_GEO_BRAVE_MAX_LOOKUPS,
        DOCTOR_FINDER_GEO_NOMINATIM_ENABLED,
        DOCTOR_FINDER_GEO_NOMINATIM_MAX_LOOKUPS,
        DOCTOR_FINDER_GEO_NOMINATIM_MIN_INTERVAL_SEC,
        DOCTOR_FINDER_GEO_ROR_CONCURRENCY,
        DOCTOR_FINDER_GEO_ROR_ENABLED,
        DOCTOR_FINDER_GEO_ROR_MIN_SCORE,
    )

    brave_key = _brave_api_key()
    ror_enabled = bool(DOCTOR_FINDER_GEO_ROR_ENABLED)
    nominatim_enabled = bool(DOCTOR_FINDER_GEO_NOMINATIM_ENABLED) and DOCTOR_FINDER_GEO_NOMINATIM_MAX_LOOKUPS > 0
    if not (ror_enabled or nominatim_enabled or brave_key):
        log.info("affiliation_georesolve: no resolver available (ROR/Nominatim off, no Brave key); skipping")
        return context

    tasks = _collect_tasks(articles)
    if not tasks:
        return context

    tup = context.get("_doctor_finder_emit")
    emit_fn: Callable[..., Any] = (lambda *a, **k: None)
    event_queue: Any = None
    if isinstance(tup, tuple) and len(tup) >= 2 and callable(tup[0]):
        emit_fn = tup[0]
        event_queue = tup[1]

    total = len(tasks)
    patches: dict[str, dict[str, Any]] = {}
    remaining = list(tasks)

    if ror_enabled and remaining:
        t0 = time.monotonic()
        before = len(patches)
        remaining = await _run_ror_stage(
            remaining,
            patches,
            concurrency=DOCTOR_FINDER_GEO_ROR_CONCURRENCY,
            min_score=DOCTOR_FINDER_GEO_ROR_MIN_SCORE,
        )
        log.info(
            "affiliation_georesolve: ror stage resolved %d/%d in %.1fs (%d remaining)",
            len(patches) - before, total, time.monotonic() - t0, len(remaining),
        )
        _emit_geo_progress(context, done=len(patches), total=total)

    if nominatim_enabled and remaining:
        t0 = time.monotonic()
        before = len(patches)
        remaining = await _run_nominatim_stage(
            remaining,
            patches,
            max_lookups=DOCTOR_FINDER_GEO_NOMINATIM_MAX_LOOKUPS,
            min_interval_sec=DOCTOR_FINDER_GEO_NOMINATIM_MIN_INTERVAL_SEC,
        )
        log.info(
            "affiliation_georesolve: nominatim stage resolved %d/%d in %.1fs (%d remaining)",
            len(patches) - before, total, time.monotonic() - t0, len(remaining),
        )
        _emit_geo_progress(context, done=len(patches), total=total)

    if brave_key and remaining and DOCTOR_FINDER_GEO_BRAVE_MAX_LOOKUPS > 0:
        t0 = time.monotonic()
        before = len(patches)
        remaining = await _run_brave_stage(
            remaining,
            patches,
            api_key=brave_key,
            context=context,
            emit_fn=emit_fn,
            event_queue=event_queue,
            max_lookups=DOCTOR_FINDER_GEO_BRAVE_MAX_LOOKUPS,
        )
        log.info(
            "affiliation_georesolve: brave stage resolved %d/%d in %.1fs (cap=%d)",
            len(patches) - before, total, time.monotonic() - t0, DOCTOR_FINDER_GEO_BRAVE_MAX_LOOKUPS,
        )

    _emit_geo_progress(context, done=total, total=total)

    if not patches:
        log.info("affiliation_georesolve: no country patches from %d affiliation(s)", total)
        return context

    resolved_by = Counter(p.get("geo_source") for p in patches.values())
    enriched = _apply_patches(articles, patches)
    log.info(
        "affiliation_georesolve: resolved %d/%d affiliation(s) [ror=%d nominatim=%d brave=%d]",
        len(patches),
        total,
        resolved_by.get("ror", 0),
        resolved_by.get("nominatim", 0),
        resolved_by.get("brave_web_llm", 0),
    )
    return {**context, "articles": enriched}
