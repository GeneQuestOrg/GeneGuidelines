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

from ._model_resolver import (
    resolve_gemma_or_fallback_spec,
    run_structured_with_ollama_fallback,
)

log = logging.getLogger(__name__)

_PUBMED = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_GEMMA_TIMEOUT_SEC = 180.0
_MAX_REVIEWS = 6


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


async def _extract_with_gemma(
    disease_name: str, abstracts: list[tuple[str, str]]
) -> tuple[_TherapyList, str]:
    primary_spec = resolve_gemma_or_fallback_spec()
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
    return await run_structured_with_ollama_fallback(
        system_prompt=_EXTRACTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        result_type=_TherapyList,
        primary_spec=primary_spec,
        max_tokens=2000,
        timeout_sec=_GEMMA_TIMEOUT_SEC,
    )


def _persist_therapies(disease_slug: str, therapies: list[_Therapy]) -> int:
    valid = {"consensus", "verified", "pending", "preclinical"}
    try:
        from ..database import get_connection
    except ImportError:
        from database import get_connection  # type: ignore[no-redef]

    inserted = 0
    conn = get_connection()
    cur = conn.cursor()
    try:
        for t in therapies:
            status = t.status.strip().lower()
            if status not in valid or not t.name.strip():
                continue
            cur.execute(
                """SELECT id FROM therapies WHERE disease_slug = ? AND LOWER(name) = LOWER(?)""",
                (disease_slug, t.name.strip()),
            )
            if cur.fetchone() is not None:
                continue
            cur.execute(
                """INSERT INTO therapies (disease_slug, name, status, note, sort_order)
                   VALUES (?, ?, ?, ?, ?)""",
                (disease_slug, t.name.strip(), status, t.note.strip(), t.sort_order),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()
    return inserted


def _log_run(
    execution_id: str,
    disease_slug: str,
    status: str,
    error: str | None = None,
    *,
    owner_clerk_id: str | None = None,
) -> None:
    try:
        from ..guideline_run_store import upsert_pipeline_run_status
    except ImportError:
        from guideline_run_store import upsert_pipeline_run_status  # type: ignore[no-redef]

    upsert_pipeline_run_status(
        execution_id=execution_id,
        pipeline="therapies_finder",
        flow_key="therapies_finder",
        disease_slug=disease_slug,
        label=f"Therapies — {disease_slug}",
        done=status in ("ready", "failed"),
        error=error,
        owner_clerk_id=owner_clerk_id,
    )


async def find_therapies_for_disease(
    disease_slug: str,
    disease_name: str,
    *,
    execution_id: str | None = None,
    owner_clerk_id: str | None = None,
) -> int:
    exec_id = execution_id or f"trp-{uuid.uuid4().hex[:12]}"
    _log_run(exec_id, disease_slug, "running", owner_clerk_id=owner_clerk_id)

    try:
        pmids = _pubmed_search_review_pmids(disease_name)
        abstracts = _pubmed_fetch_abstracts(pmids)
    except Exception as exc:
        log.exception("PubMed lookup failed for therapies of %s", disease_name)
        _log_run(exec_id, disease_slug, "failed", error=f"pubmed: {exc}", owner_clerk_id=owner_clerk_id)
        return 0

    if not abstracts:
        _log_run(exec_id, disease_slug, "ready", owner_clerk_id=owner_clerk_id)
        return 0

    try:
        result, model_spec = await _extract_with_gemma(disease_name, abstracts)
    except Exception as exc:
        log.exception("Gemma extraction failed for therapies of %s", disease_name)
        _log_run(exec_id, disease_slug, "failed", error=f"extractor: {exc}", owner_clerk_id=owner_clerk_id)
        return 0

    inserted = _persist_therapies(disease_slug, result.therapies)
    _log_run(exec_id, disease_slug, "ready", owner_clerk_id=owner_clerk_id)
    log.info(
        "therapies_finder: %d candidate(s), %d inserted (model=%s)",
        len(result.therapies),
        inserted,
        model_spec,
    )
    return inserted


__all__ = ["find_therapies_for_disease"]
