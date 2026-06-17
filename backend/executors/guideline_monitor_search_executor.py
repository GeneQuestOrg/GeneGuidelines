"""Executor for the ``guideline_monitor_search`` node — the level-b monitor's entry.

Loads the disease's CURRENT synthesis (what the guideline already says — the
reference a delta must go beyond) + the shelf PMIDs to exclude, then searches
recent literature *beyond the shelf*. Bounded by design (these candidates get full
triage + delta treatment, so the set is small) — budget discipline lives here.

Requires a synthesis to exist (level b updates an existing level-a guideline).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import os
import urllib.parse
import urllib.request

from .base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_RECENT_YEARS = 3
_MAX_CANDIDATES = 12
_ABSTRACT_CHARS = 240
_GUIDANCE_PARA_CHARS = 220


class GuidelineMonitorSearchExecutor(NodeExecutor):
    """Load current guidance + recent non-shelf papers for the monitor."""

    def __init__(self, repo=None) -> None:
        self._repo = repo  # injectable for tests

    @classmethod
    def node_type(cls) -> str:
        return "guideline_monitor_search"

    def _get_repo(self):
        if self._repo is not None:
            return self._repo
        from ..guidelines.repository import SqlaGuidelinesRepo

        return SqlaGuidelinesRepo()

    async def execute(self, input: NodeInput) -> NodeOutput:
        initial = input.initial_data or input.context.get("initial") or {}
        slug = str(initial.get("disease_slug") or "").strip().lower()
        disease_name = str(initial.get("disease_name") or slug).strip() or slug
        if not slug:
            return NodeOutput(data={"ok": False, "error": "disease_slug missing in flow context."})

        loop = asyncio.get_event_loop()
        repo = self._get_repo()
        synthesis = await loop.run_in_executor(None, lambda: repo.get_synthesis(slug))
        if synthesis is None:
            return NodeOutput(
                data={
                    "ok": False,
                    "error": f"No synthesis for '{slug}' — build the level-(a) synthesis before monitoring (level b).",
                }
            )
        docs = await loop.run_in_executor(None, lambda: repo.list_source_documents(slug))
        shelf_pmids = {str(d.pmid).strip() for d in docs if str(getattr(d, "pmid", "") or "").strip()}

        current_guidance, sections = _condense_synthesis(synthesis)

        try:
            candidates = await loop.run_in_executor(
                None, lambda: _recent_candidates(disease_name, shelf_pmids)
            )
        except Exception as exc:  # noqa: BLE001 — no candidates → nothing to monitor, surface it
            log.warning("guideline_monitor_search: retrieval failed for %s: %s", disease_name, exc)
            return NodeOutput(data={"ok": False, "error": f"monitor search failed: {exc}"})

        return NodeOutput(
            data={
                "ok": True,
                "slug": slug,
                "current_guidance": current_guidance,
                "sections": sections,
                "candidates": candidates,
                "candidate_count": len(candidates),
                "shelf_pmids": sorted(shelf_pmids),
            }
        )


def _condense_synthesis(synthesis) -> tuple[str, list[dict]]:
    """Compact 'what the guideline already says' text + the section id/title list."""
    lines: list[str] = []
    sections: list[dict] = []
    for sec in synthesis.sections or []:
        if not isinstance(sec, dict):
            continue
        sid = str(sec.get("id") or "")
        title = str(sec.get("title") or sid)
        sections.append({"id": sid, "title": title})
        lines.append(f"## {title}")
        intro = str(sec.get("intro") or "").strip()
        if intro:
            lines.append(intro)
        for para in (sec.get("paragraphs") or [])[:6]:
            if isinstance(para, dict):
                txt = str(para.get("text") or "").strip()[:_GUIDANCE_PARA_CHARS]
                if txt:
                    lines.append(f"- {txt}")
    return "\n".join(lines), sections


# ── retrieval helpers (module-level so tests can monkeypatch) ──────────────


def _http_get_json(url: str) -> dict:
    key = (os.environ.get("NCBI_API_KEY") or "").strip()
    if key:
        url = f"{url}&api_key={key}"
    req = urllib.request.Request(url, headers={"User-Agent": "GeneGuidelines/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _recent_candidates(disease_name: str, exclude_pmids: set[str]) -> list[dict]:
    """Recent papers (last _RECENT_YEARS) for the disease, excluding the shelf."""
    from ..tools.pubmed_runtime import fetch_article_details_impl

    year_to = _dt.date.today().year
    year_from = year_to - _RECENT_YEARS
    term = f'"{disease_name}"[Title/Abstract] AND {year_from}:{year_to}[dp] AND Review[ptyp]'
    qs = urllib.parse.urlencode(
        {"db": "pubmed", "term": term, "retmode": "json", "retmax": 30, "sort": "date"}
    )
    ids = list(_http_get_json(f"{_EUTILS}/esearch.fcgi?{qs}").get("esearchresult", {}).get("idlist", []))
    fresh = [p for p in ids if p not in exclude_pmids][:_MAX_CANDIDATES]
    if not fresh:
        return []
    arts = fetch_article_details_impl(fresh, include_abstracts=True)
    out: list[dict] = []
    for a in arts.get("articles") or []:
        pmid = str(a.get("pmid") or "").strip()
        if not pmid or pmid in exclude_pmids:
            continue
        out.append(
            {
                "pmid": pmid,
                "title": a.get("title") or "",
                "authors": a.get("authors") or "",
                "journal": a.get("source") or "",
                "year": (str(a.get("pubdate") or "").split() or [""])[0],
                "abstract": (a.get("abstract") or "")[:_ABSTRACT_CHARS],
            }
        )
    return out
