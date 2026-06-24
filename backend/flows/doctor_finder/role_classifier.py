from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any, Optional

import httpx

from ...config import (
    DOCTOR_FINDER_CT_CONCURRENCY,
    DOCTOR_FINDER_CT_MAX_AUTHORS,
    DOCTOR_FINDER_CT_PROGRESS_EVERY,
)

from .schemas import AuthorFlags, AuthorRole

log = logging.getLogger(__name__)

CLINICALTRIALS_API_V2_BASE = "https://clinicaltrials.gov/api/v2/studies"
CLINICALTRIALS_TIMEOUT_SEC = 5.0
_CT_CACHE: dict[tuple[str, str, str], bool] = {}  # in-memory, process-scoped
_CT_CACHE_MAXSIZE = 1000

_DOCTOR_FINDER_PROGRESS_KIND = "doctor_finder_progress"


def _emit_ct_progress(context: dict[str, Any], *, done: int, total: int) -> None:
    """Best-effort SSE progress for long ClinicalTrials phases."""
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
            "stage": "role_classifier_ct",
            "done": done,
            "total": total,
        },
    )


async def _check_clinical_trial(
    last_name: str,
    initials: str,
    disease_name: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Query ClinicalTrials.gov v2 API for trials involving the author. Returns False on any error."""
    cache_key = (last_name.lower(), initials[:1].lower() if initials else "", disease_name.lower())
    if cache_key in _CT_CACHE:
        return _CT_CACHE[cache_key]

    async def _do_request(c: httpx.AsyncClient) -> bool:
        try:
            params = {
                "query.term": f"{last_name} {disease_name}",
                "filter.overallStatus": "RECRUITING,ACTIVE_NOT_RECRUITING,COMPLETED",
                "pageSize": 1,
                "format": "json",
            }
            resp = await c.get(CLINICALTRIALS_API_V2_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
            total = int(data.get("totalCount", 0) or 0)
            return total > 0
        except Exception as exc:
            log.debug("clinicaltrials_check_failed last_name=%s error=%s", last_name, exc)
            return False

    if client is not None:
        result = await _do_request(client)
    else:
        async with httpx.AsyncClient(timeout=CLINICALTRIALS_TIMEOUT_SEC) as c:
            result = await _do_request(c)

    if len(_CT_CACHE) >= _CT_CACHE_MAXSIZE:
        _CT_CACHE.pop(next(iter(_CT_CACHE)))
    _CT_CACHE[cache_key] = result
    return result


def _build_justification(author: dict, role: str, flags: AuthorFlags) -> str:
    """Build a programmatic justification string from role and flags."""
    parts = [f"Role: {role}."]
    if flags.guideline_author:
        parts.append(f"Co-authored {author['guideline_count']} guideline(s).")
    if flags.active_last_2y:
        parts.append("Active in the last 2 years.")
    if flags.runs_clinical_trial:
        parts.append("Runs clinical trials.")
    if flags.international_collab:
        parts.append("International collaborations.")
    return " ".join(parts)


def _assign_role(gc: int, rc: int, oc: int, pc: int, cc: int, active: bool) -> str:
    """Return the first matching role name per cascade rules.

    ``active_contributor`` requires real volume of disease-relevant work — at least
    two original papers, an original plus a review, or three+ papers total. A single
    review (or one incidental paper) does NOT make someone a contributor; with the
    article-level relevance gate it should rarely happen, but this is the second line
    of defence so a lone paper ranks as ``peripheral`` rather than masquerading as a
    specialist.
    """
    if gc >= 1:
        return "guideline_author"
    if rc >= 2 or oc >= 5 or pc >= 10:
        return "senior_investigator"
    if active and (oc >= 2 or (oc >= 1 and rc >= 1) or pc >= 3):
        return "active_contributor"
    if cc >= 1:
        return "case_reporter"
    return "peripheral"


def _author_active_and_intl(author: dict, *, now: date) -> tuple[bool, bool]:
    papers = author.get("papers", [])
    years = [p["year"] for p in papers if isinstance(p.get("year"), int)]
    active = bool(years) and max(years) >= (now.year - 2)

    countries_in_papers: set[str] = set()
    for p in papers:
        pa = p.get("parsed_affiliation")
        if isinstance(pa, dict) and pa.get("country_code"):
            countries_in_papers.add(pa["country_code"])
    intl = len(countries_in_papers) >= 2
    return active, intl


async def run_async(context: dict, *, now: Optional[date] = None) -> dict:
    """Classify roles and set flags for all aggregated_authors. Returns new context dict."""
    if now is None:
        now = date.today()

    work = dict(context)
    disease_name = (work.get("initial", {}) or {}).get("disease_name", "") or ""
    authors_raw = work.get("aggregated_authors", [])
    n = len(authors_raw)

    # Indices sorted by publication volume — ClinicalTrials budget applies to the busiest authors first.
    sorted_by_papers = sorted(
        range(n),
        key=lambda i: int(authors_raw[i].get("paper_count") or 0),
        reverse=True,
    )
    ct_indices = sorted_by_papers[: min(n, DOCTOR_FINDER_CT_MAX_AUTHORS)]
    skipped_ct = n - len(ct_indices)

    log.info(
        "role_classifier: %d authors; CT API for %d (cap=%d, concurrency=%d); %d skip CT=False",
        n,
        len(ct_indices),
        DOCTOR_FINDER_CT_MAX_AUTHORS,
        DOCTOR_FINDER_CT_CONCURRENCY,
        skipped_ct,
    )
    _emit_ct_progress(work, done=0, total=len(ct_indices))

    ct_by_index: dict[int, bool] = {i: False for i in range(n)}
    if ct_indices:
        sem = asyncio.Semaphore(DOCTOR_FINDER_CT_CONCURRENCY)
        done_lock = asyncio.Lock()
        done_ct = 0

        async with httpx.AsyncClient(timeout=CLINICALTRIALS_TIMEOUT_SEC) as shared_client:

            async def check_one(idx: int) -> None:
                nonlocal done_ct
                author = authors_raw[idx]
                async with sem:
                    ct = await _check_clinical_trial(
                        str(author.get("last_name", "")),
                        str(author.get("initials", "")),
                        disease_name,
                        client=shared_client,
                    )
                ct_by_index[idx] = ct
                async with done_lock:
                    done_ct += 1
                    d = done_ct
                if (
                    d == 1
                    or d == len(ct_indices)
                    or d % DOCTOR_FINDER_CT_PROGRESS_EVERY == 0
                ):
                    _emit_ct_progress(work, done=d, total=len(ct_indices))

            await asyncio.gather(*(check_one(i) for i in ct_indices))

    enriched = []
    for idx, raw in enumerate(authors_raw):
        author = dict(raw)
        active, intl = _author_active_and_intl(author, now=now)
        ct = ct_by_index[idx]

        flags = AuthorFlags(
            guideline_author=author.get("guideline_count", 0) >= 1,
            cites_current_guidelines=False,
            active_last_2y=active,
            runs_clinical_trial=ct,
            international_collab=intl,
        )

        gc = author.get("guideline_count", 0)
        rc = author.get("review_count", 0)
        oc = author.get("original_count", 0)
        pc = author.get("paper_count", 0)
        cc = author.get("case_report_count", 0)

        role_name = _assign_role(gc, rc, oc, pc, cc, active)
        justification = _build_justification(author, role_name, flags)
        role = AuthorRole(role=role_name, justification=justification)

        author["flags"] = flags.model_dump()
        author["role"] = role.model_dump()
        enriched.append(author)

    work.pop("_doctor_finder_emit", None)
    return {**work, "aggregated_authors": enriched}
