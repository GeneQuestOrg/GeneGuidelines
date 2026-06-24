"""Extract therapy lines for a disease from PubMed review literature using Gemma.

Pattern mirrors :mod:`backend.services.official_guidelines_finder`:

1. Query PubMed E-utilities for recent reviews / guidelines on the disease.
2. Pull abstracts via efetch.
3. Gemma 4 (structured output) reads the abstracts and proposes therapy
   entries, each tagged with one of four status values:
   ``consensus`` / ``verified`` / ``pending`` / ``preclinical``.
4. Persist new rows to ``therapies`` (disease_slug FK).

The four-state status maps to the existing public detail page badge.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from ..config import FINDER_LLM_TIMEOUT_SEC
from ._model_resolver import (
    resolve_gemma_or_fallback_spec,
    run_structured_with_ollama_fallback,
)

log = logging.getLogger(__name__)

_PUBMED = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_MAX_REVIEWS = 15
_EXTRACT_BATCH_SIZE = 5
_EXTRACT_MAX_RETRIES = 1


class _Therapy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Therapy name, drug, or intervention as written in literature.")
    status: str = Field(
        ...,
        description=(
            "One of: consensus (multi-society guideline-endorsed), "
            "verified (RCT or large cohort evidence), "
            "pending (smaller trials or case series), "
            "preclinical (animal/in-vitro only)."
        ),
    )
    note: str = Field(..., description="One concise clinical sentence: indication, line, key caveat. No PII, no dates.")
    sort_order: int = Field(100, description="Lower = more important. 10/20/30 for consensus, 100 default.")
    pmids: list[str] = Field(default_factory=list, description="PubMed IDs of the reviews that support this therapy line.")


class _TherapyList(BaseModel):
    model_config = ConfigDict(extra="forbid")
    therapies: list[_Therapy] = Field(default_factory=list)


_EXTRACTION_SYSTEM_PROMPT = """\
You extract therapy lines for a rare disease from PubMed review abstracts.

Rules:
- Status is exactly one of: consensus / verified / pending / preclinical.
  * consensus  = recommended by multi-society guideline or international consensus paper.
  * verified   = supported by RCT, controlled trial, or substantial cohort.
  * pending    = small trial, case series, or expert opinion only.
  * preclinical = animal / in-vitro / mechanistic only — not in patients.
- One sentence ``note``: indication, line of therapy, key caveat. No PII.
  Avoid absolute dates. Avoid product brand names unless mechanistically distinct.
- Deduplicate. If two abstracts mention "alendronate" and "bisphosphonates", combine
  under the broader name unless the specifics differ.
- Sort order: 10 for first-line consensus drugs, 20 for second-line, 30 for adjunct,
  100 (default) for everything else. Lower numbers surface first in the UI.
- ``pmids``: list every PMID that supports this therapy line. Copy them from the
  [PMID XXXXXX] markers in the input — do not invent PMIDs.
- Return 0–8 therapies. Quality over quantity.
"""


def _pubmed_search_review_pmids(disease_name: str) -> list[str]:
    params = {
        "db": "pubmed",
        "term": f'"{disease_name}"[Title/Abstract] AND (review[Publication Type] OR guideline[Publication Type])',
        "retmax": _MAX_REVIEWS,
        "sort": "relevance",
        "retmode": "json",
    }
    url = f"{_PUBMED}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "GeneGuidelines/0.1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    return list(data.get("esearchresult", {}).get("idlist", []))


def _pubmed_fetch_abstracts(pmids: list[str]) -> list[tuple[str, str]]:
    if not pmids:
        return []
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "abstract",
        "retmode": "xml",
    }
    url = f"{_PUBMED}/efetch.fcgi?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "GeneGuidelines/0.1"})
    with urllib.request.urlopen(req, timeout=25) as r:
        xml_text = r.read().decode("utf-8", errors="replace")
    tree = ET.fromstring(xml_text)
    out: list[tuple[str, str]] = []
    for article in tree.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        title_el = article.find(".//ArticleTitle")
        abstract_parts = [
            (a.text or "").strip()
            for a in article.findall(".//Abstract/AbstractText")
            if a is not None
        ]
        if pmid_el is None or title_el is None:
            continue
        title = (title_el.text or "").strip()
        abstract = " ".join(p for p in abstract_parts if p)
        if not abstract:
            continue
        out.append((pmid_el.text or "", f"{title}\n\n{abstract}"))
    return out


async def _extract_batch_with_gemma(
    disease_name: str,
    abstracts: list[tuple[str, str]],
    *,
    primary_spec: str,
) -> tuple[list[_Therapy], str, bool]:
    _ws_re = re.compile(r"\s+")
    bundle = "\n\n---\n\n".join(
        "[PMID " + pmid + "]\n" + _ws_re.sub(" ", body)[:2400]
        for pmid, body in abstracts
    )
    user_prompt = (
        f"Disease: {disease_name}\n\n"
        f"PubMed reviews (excerpts):\n\n{bundle}\n\n"
        "Extract therapy lines per the rules. Up to 8."
    )
    last_exc: Exception | None = None
    for attempt in range(_EXTRACT_MAX_RETRIES + 1):
        try:
            result, model_spec = await run_structured_with_ollama_fallback(
                system_prompt=_EXTRACTION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                result_type=_TherapyList,
                primary_spec=primary_spec,
                max_tokens=2000,
                timeout_sec=FINDER_LLM_TIMEOUT_SEC,
            )
            return list(result.therapies), model_spec, False
        except (asyncio.TimeoutError, TimeoutError) as exc:
            last_exc = exc
            if attempt < _EXTRACT_MAX_RETRIES:
                log.warning(
                    "therapies_finder: batch LLM timeout (attempt %d), retrying",
                    attempt + 1,
                )
                continue
        except Exception as exc:
            last_exc = exc
            break
    log.warning(
        "therapies_finder: batch LLM failed (%s), using PubMed title fallback for %d review(s)",
        last_exc,
        len(abstracts),
    )
    return _fallback_therapies_from_abstracts(abstracts), primary_spec, True


def _fallback_therapies_from_abstracts(
    abstracts: list[tuple[str, str]],
) -> list[_Therapy]:
    """When Gemma times out, surface review-derived placeholders rather than an empty page."""
    therapies: list[_Therapy] = []
    seen: set[str] = set()
    for pmid, body in abstracts:
        title = body.split("\n\n", 1)[0].strip()
        if len(title) < 8:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        abstract_tail = body.split("\n\n", 1)[-1].strip()
        note = abstract_tail[:220].strip()
        if not note:
            note = f"Identified from PubMed review PMID {pmid}; pending structured extraction."
        else:
            note = f"{note} (PMID {pmid})"
        therapies.append(
            _Therapy(
                name=title[:100],
                status="pending",
                note=note,
                sort_order=100,
                pmids=[pmid] if pmid else [],
            )
        )
    return therapies


async def _extract_with_gemma(
    disease_name: str, abstracts: list[tuple[str, str]]
) -> tuple[_TherapyList, str, bool]:
    primary_spec = resolve_gemma_or_fallback_spec()
    merged: list[_Therapy] = []
    used_fallback = False
    model_spec = primary_spec
    for offset in range(0, len(abstracts), _EXTRACT_BATCH_SIZE):
        batch = abstracts[offset : offset + _EXTRACT_BATCH_SIZE]
        batch_therapies, model_spec, batch_fallback = await _extract_batch_with_gemma(
            disease_name,
            batch,
            primary_spec=primary_spec,
        )
        merged.extend(batch_therapies)
        used_fallback = used_fallback or batch_fallback
    return _TherapyList(therapies=merged), model_spec, used_fallback


def _words(name: str) -> set[str]:
    """Significant lowercase words (>4 chars) from a therapy name."""
    return {w.lower() for w in re.split(r"\W+", name) if len(w) > 4}


# Words that are too common in medical abstracts to discriminate which papers
# support a specific therapy.  Used by both backfill helpers to avoid assigning
# monitoring/assessment entries a citation that is really about a drug.
_BACKFILL_EXCLUDED_WORDS: frozenset[str] = frozenset({
    "observation", "monitoring", "treatment", "therapy", "clinical",
    "protocol", "management", "diagnosis", "standard", "indications",
    "disease", "syndrome", "disorder", "condition", "symptoms",
    "calcium", "phosphate", "endocrine", "hormone", "patients", "patient",
    "effects", "changes", "results", "outcome", "growth",
})


def _clean_pmids(raw: list[str]) -> list[str]:
    """Validate and deduplicate PubMed IDs (numeric strings, 4–10 digits)."""
    seen: dict[str, None] = {}
    for p in raw:
        s = p.strip()
        if re.fullmatch(r"\d{4,10}", s):
            seen[s] = None
    return list(seen)


def _specific_keywords(name: str) -> list[str]:
    """Return keywords from a therapy name that are long and specific enough
    to anchor a PubMed citation.  Generic clinical terms are excluded."""
    return [
        w.lower()
        for w in re.split(r"[\W_]+", name)
        if len(w) >= 6 and w.lower() not in _BACKFILL_EXCLUDED_WORDS
    ]


def _backfill_pmids_from_abstracts(
    therapies: list[_Therapy],
    abstracts: list[tuple[str, str]],
) -> list[_Therapy]:
    """Assign PMIDs to therapies that the LLM left blank.

    Scans each abstract for therapy-name keywords via case-insensitive substring
    match. More reliable than asking a small LLM to track citations, because
    specific drug names (bisphosphonates, denosumab, trametinib …) appear
    verbatim in the supporting articles.  Generic monitoring/assessment entries
    (no specific keywords) are left untouched to avoid false citations.
    """
    result: list[_Therapy] = []
    for t in therapies:
        if t.pmids:
            result.append(t)
            continue
        keywords = _specific_keywords(t.name)
        if not keywords:
            result.append(t)
            continue
        matched = _clean_pmids([
            pmid
            for pmid, text in abstracts
            if any(kw in text.lower() for kw in keywords)
        ])
        result.append(
            _Therapy(
                name=t.name,
                status=t.status,
                note=t.note,
                sort_order=t.sort_order,
                pmids=matched,
            )
        )
    return result


def _backfill_seed_rows_from_abstracts(
    disease_slug: str,
    abstracts: list[tuple[str, str]],
) -> int:
    """Direct backfill: scan existing DB rows that still have no PMIDs and match
    against abstract text by keyword.  Called after _persist_therapies so that
    seed rows the LLM missed or renamed are still linked to their literature.
    Entries whose names contain no specific drug keywords are intentionally
    skipped — assigning monitoring/assessment entries broad citations would be
    misleading on a clinical page."""
    try:
        from ..database import get_connection
    except ImportError:
        from database import get_connection  # type: ignore[no-redef]

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, name, pmids_json FROM therapies WHERE disease_slug = %s",
            (disease_slug,),
        )
        rows = cur.fetchall()
        updated = 0
        for row in rows:
            if json.loads(row["pmids_json"] or "[]"):
                continue
            keywords = _specific_keywords(row["name"])
            if not keywords:
                continue
            clean = _clean_pmids([
                pmid
                for pmid, text in abstracts
                if any(kw in text.lower() for kw in keywords)
            ])
            if not clean:
                continue
            cur.execute(
                "UPDATE therapies SET pmids_json = %s WHERE id = %s",
                (json.dumps(clean), row["id"]),
            )
            updated += 1
        conn.commit()
        return updated
    finally:
        conn.close()


def _persist_therapies(disease_slug: str, therapies: list[_Therapy]) -> int:
    valid = {"consensus", "verified", "pending", "preclinical"}
    try:
        from ..database import get_connection
    except ImportError:
        from database import get_connection  # type: ignore[no-redef]

    conn = get_connection()
    cur = conn.cursor()
    try:
        # If the disease already has therapies (e.g. from seed data), only
        # update PMIDs on matching rows — don't insert LLM-generated duplicates.
        cur.execute(
            "SELECT id, name, pmids_json FROM therapies WHERE disease_slug = %s",
            (disease_slug,),
        )
        existing = cur.fetchall()
        if existing:
            # Intentional: for seeded diseases we only merge newly discovered
            # PMIDs onto matching rows.  We do NOT insert LLM-generated rows,
            # because seed data is curated and LLM names rarely match exactly —
            # doing so previously created duplicates (e.g. "bisphosphonates" vs
            # "Bisphosphonates (pamidronate, zoledronate)").  New therapy lines
            # should be added via the seed file or a manual content PR.
            updated = 0
            for t in therapies:
                clean_pmids = _clean_pmids(t.pmids)
                if not clean_pmids:
                    continue
                t_words = _words(t.name)
                for row in existing:
                    row_id, row_name, row_pmids_json = row["id"], row["name"], row["pmids_json"]
                    if t_words & _words(row_name):
                        existing_pmids = json.loads(row_pmids_json or "[]")
                        merged = _clean_pmids(existing_pmids + clean_pmids)
                        cur.execute(
                            "UPDATE therapies SET pmids_json = %s WHERE id = %s",
                            (json.dumps(merged), row_id),
                        )
                        updated += 1
                        break
            conn.commit()
            return updated

        # No existing therapies — insert LLM results as new rows.
        inserted = 0
        for t in therapies:
            status = t.status.strip().lower()
            if status not in valid or not t.name.strip():
                continue
            cur.execute(
                "SELECT id FROM therapies WHERE disease_slug = %s AND LOWER(name) = LOWER(%s)",
                (disease_slug, t.name.strip()),
            )
            if cur.fetchone() is not None:
                continue
            clean_pmids = [p.strip() for p in t.pmids if re.fullmatch(r"\d{4,10}", p.strip())]
            cur.execute(
                """INSERT INTO therapies (disease_slug, name, status, note, sort_order, pmids_json)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (disease_slug, t.name.strip(), status, t.note.strip(), t.sort_order, json.dumps(clean_pmids)),
            )
            inserted += 1
        conn.commit()
        return inserted
    finally:
        conn.close()


def _log_run(execution_id: str, disease_slug: str, status: str, error: str | None = None) -> None:
    try:
        from ..database import get_connection
    except ImportError:
        from database import get_connection  # type: ignore[no-redef]

    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    try:
        cur.execute("SELECT 1 FROM guideline_run_results WHERE execution_id = %s", (execution_id,))
        if cur.fetchone() is None:
            cur.execute(
                """INSERT INTO guideline_run_results
                   (execution_id, pipeline, flow_key, disease_slug, label,
                    done, started_at, finished_at, error)
                   VALUES (%s, 'therapies_finder', 'therapies_finder', %s, %s, %s, %s, %s, %s)""",
                (
                    execution_id,
                    disease_slug,
                    f"Therapies — {disease_slug}",
                    1 if status in ("ready", "failed") else 0,
                    now,
                    now if status in ("ready", "failed") else None,
                    error,
                ),
            )
        else:
            cur.execute(
                """UPDATE guideline_run_results
                   SET done = %s, finished_at = %s, error = COALESCE(%s, error)
                   WHERE execution_id = %s""",
                (
                    1 if status in ("ready", "failed") else 0,
                    now if status in ("ready", "failed") else None,
                    error,
                    execution_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


async def find_therapies_for_disease(
    disease_slug: str,
    disease_name: str,
    *,
    execution_id: str | None = None,
) -> int:
    exec_id = execution_id or f"trp-{uuid.uuid4().hex[:12]}"
    _log_run(exec_id, disease_slug, "running")

    try:
        pmids = _pubmed_search_review_pmids(disease_name)
        abstracts = _pubmed_fetch_abstracts(pmids)
    except Exception as exc:
        log.exception("PubMed lookup failed for therapies of %s", disease_name)
        _log_run(exec_id, disease_slug, "failed", error=f"pubmed: {exc}")
        return 0

    if not abstracts:
        _log_run(exec_id, disease_slug, "ready")
        return 0

    try:
        result, model_spec, used_fallback = await _extract_with_gemma(disease_name, abstracts)
    except Exception as exc:
        log.exception("Gemma extraction failed for therapies of %s", disease_name)
        fallback = _fallback_therapies_from_abstracts(abstracts)
        inserted = _persist_therapies(disease_slug, fallback)
        _backfill_seed_rows_from_abstracts(disease_slug, abstracts)
        _log_run(exec_id, disease_slug, "ready")
        log.warning(
            "therapies_finder: LLM unavailable, persisted %d therapy placeholder(s) from PubMed",
            inserted,
        )
        return inserted

    therapies_with_pmids = _backfill_pmids_from_abstracts(result.therapies, abstracts)
    inserted = _persist_therapies(disease_slug, therapies_with_pmids)
    seed_backfilled = _backfill_seed_rows_from_abstracts(disease_slug, abstracts)
    _log_run(exec_id, disease_slug, "ready")
    log.info(
        "therapies_finder: %d candidate(s), %d inserted, %d seed rows backfilled (model=%s, fallback=%s)",
        len(result.therapies),
        inserted,
        seed_backfilled,
        model_spec,
        used_fallback,
    )
    return inserted


__all__ = ["find_therapies_for_disease"]
