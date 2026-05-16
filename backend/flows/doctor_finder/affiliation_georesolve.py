"""Brave web search + structured LLM: infer country/continent for PubMed affiliations missing ISO2."""
from __future__ import annotations

import asyncio
import hashlib
import logging
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


def _patch_from_iso2(iso2: str, confidence: float) -> dict[str, Any]:
    c = pycountry.countries.get(alpha_2=iso2)
    name = c.name if c else iso2
    cont = continent_for_iso_alpha2(iso2)
    return {
        "country_code": iso2,
        "country_name": name,
        "continent": cont,
        "geo_source": "brave_web_llm",
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


async def run_async(context: dict[str, Any]) -> dict[str, Any]:
    """Enrich ``articles[*].authors[*].parsed_affiliation`` with Brave+LLM country when ISO2 was missing."""
    articles = list(context.get("articles") or [])
    if not articles:
        return context

    api_key = _brave_api_key()
    if not api_key:
        log.info("affiliation_georesolve: BRAVE_API_KEY not set; skipping Brave+LLM geo step")
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
    model_spec = _model_spec(context)
    store: dict[str, Any] = {}
    total = len(tasks)
    sem = asyncio.Semaphore(DOCTOR_FINDER_GEO_BRAVE_CONCURRENCY)
    patches: dict[str, dict[str, Any]] = {}
    done = 0

    async def _bounded(t: tuple[str, str, str | None]) -> None:
        nonlocal done
        key, raw, inst = t
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    patch = await _resolve_one(
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
                if patch:
                    patches[key] = patch
            finally:
                done += 1
                if done % 5 == 0 or done == total:
                    _emit_geo_progress(context, done=done, total=total)

    await asyncio.gather(*(_bounded(t) for t in tasks))

    if not patches:
        log.info("affiliation_georesolve: no high-confidence patches from %d affiliation(s)", total)
        return context

    enriched = _apply_patches(articles, patches)
    log.info(
        "affiliation_georesolve: applied %d unique affiliation patch(es) from %d Brave+LLM attempt(s)",
        len(patches),
        total,
    )
    return {**context, "articles": enriched}
