"""Executor for the ``guideline_shelf_search`` node — the shelf-builder's retrieval.

Casts a deliberately broad net over PubMed (consensus / guideline / management
reviews + recent reviews) and NCBI Bookshelf (continuously-updated compendia like
GeneReviews), de-dupes, and hands a candidate list to the classify node. Recall
matters more than precision here — the LLM classify step picks what belongs on the
shelf and the role of each; extra candidates are fine.

Reads ``disease_name`` from the flow's initial context. Network failure is hard
(no candidates → no shelf), so it surfaces an error rather than passing silently.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
import urllib.request

from .base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_RETMAX_PER_QUERY = 25
# Budget discipline: cap the candidate set handed to the classify LLM. Queries are
# interleaved round-robin so each query's top hits survive the cap (recall-safe —
# validated by scripts/validate_shelf_fd.py). Abstracts are trimmed to keep the
# prompt small. The vllm/Gemma effective prompt cap is ~60k tokens; budget is
# bounded by the CANDIDATE COUNT, not by truncating abstracts (medical tool).
_PUBMED_CANDIDATE_CAP = 30
_MAX_BOOKS = 8


class GuidelineShelfSearchExecutor(NodeExecutor):
    """Retrieve candidate source documents (PubMed + Bookshelf) for a disease."""

    @classmethod
    def node_type(cls) -> str:
        return "guideline_shelf_search"

    async def execute(self, input: NodeInput) -> NodeOutput:
        initial = input.initial_data or input.context.get("initial") or {}
        disease_name = str(initial.get("disease_name") or "").strip()
        if not disease_name:
            return NodeOutput(
                data={"ok": False, "error": "disease_name missing in flow context."}
            )

        loop = asyncio.get_event_loop()
        try:
            candidates = await loop.run_in_executor(
                None, lambda: _collect_shelf_candidates(disease_name)
            )
        except Exception as exc:  # noqa: BLE001 — no candidates means no shelf; surface it
            log.warning("guideline_shelf_search: retrieval failed for %s: %s", disease_name, exc)
            return NodeOutput(data={"ok": False, "error": f"shelf search failed: {exc}"})

        if not candidates:
            return NodeOutput(
                data={"ok": False, "error": f"no candidates found for {disease_name!r}.", "candidates": []}
            )
        return NodeOutput(
            data={"ok": True, "candidates": candidates, "candidate_count": len(candidates)}
        )


# ── retrieval helpers (module-level so tests can monkeypatch) ──────────────


def _api_key() -> str:
    return (os.environ.get("NCBI_API_KEY") or "").strip()


def _http_get_json(url: str) -> dict:
    key = _api_key()
    if key:
        url = f"{url}&api_key={key}"  # raises E-utilities rate limits, avoids 429
    req = urllib.request.Request(url, headers={"User-Agent": "GeneGuidelines/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _esearch_ids(db: str, term: str, retmax: int) -> list[str]:
    qs = urllib.parse.urlencode(
        {"db": db, "term": term, "retmode": "json", "retmax": retmax, "sort": "relevance"}
    )
    data = _http_get_json(f"{_EUTILS}/esearch.fcgi?{qs}")
    return list(data.get("esearchresult", {}).get("idlist", []))


def _book_accession(rec: dict) -> str:
    """The NBK accession of a books esummary record (chapter-level preferred)."""
    for key in ("accessionid", "chapteraccessionid", "bookaccessionid"):
        acc = str(rec.get(key) or "").strip()
        if acc.upper().startswith("NBK"):
            return acc
    return ""


def _book_candidates(disease_name: str) -> list[dict]:
    """NCBI Bookshelf compendia for the disease — GeneReviews (gene[book]) first.

    The esearch UID is NOT the NBK accession; the accession lives in the esummary
    ``accessionid`` / ``chapteraccessionid`` field.
    """
    ids: list[str] = []
    seen: set[str] = set()
    for term in (f'"{disease_name}" AND gene[book]', f'"{disease_name}"'):
        try:
            for bid in _esearch_ids("books", term, _MAX_BOOKS):
                if bid not in seen:
                    seen.add(bid)
                    ids.append(bid)
        except Exception as exc:  # noqa: BLE001
            log.debug("guideline_shelf_search: books esearch failed for %r: %s", term, exc)
    if not ids:
        return []
    qs = urllib.parse.urlencode({"db": "books", "id": ",".join(ids), "retmode": "json"})
    block = _http_get_json(f"{_EUTILS}/esummary.fcgi?{qs}").get("result", {})
    out: list[dict] = []
    for bid in ids:
        rec = block.get(bid) or {}
        accession = _book_accession(rec)
        if not accession:  # no real NBK id → not a citable compendium entry
            continue
        out.append(
            {
                "bookshelf": accession,
                "title": (rec.get("title") or "").rstrip("."),
                "authors": ", ".join(a.get("name", "") for a in (rec.get("authors") or [])[:5]),
                "journal": (rec.get("book") or "NCBI Bookshelf"),
                "year": rec.get("pubdate") or "continuously updated",
                "abstract": "",
            }
        )
    return out


def _collect_shelf_candidates(disease_name: str) -> list[dict]:
    """Broad multi-query retrieval → de-duped candidate list with metadata."""
    from ..tools.pubmed_runtime import fetch_article_details_impl

    queries = [
        f'"{disease_name}"[Title/Abstract] AND (consensus OR guideline OR "best practice")',
        f'"{disease_name}"[Title/Abstract] AND Review[ptyp] AND 2018:2026[dp]',
        f'"{disease_name}"[Title/Abstract] AND (management OR therapy OR treatment) AND Review[ptyp]',
    ]
    per_query: list[list[str]] = []
    for term in queries:
        try:
            per_query.append(_esearch_ids("pubmed", term, _RETMAX_PER_QUERY))
        except Exception as exc:  # noqa: BLE001 — one failed query shouldn't sink the rest
            log.debug("guideline_shelf_search: esearch failed for %r: %s", term, exc)
            per_query.append([])

    # Round-robin interleave so each query's top hits survive the cap.
    pmids: list[str] = []
    seen: set[str] = set()
    for rank in range(_RETMAX_PER_QUERY):
        for ids in per_query:
            if rank < len(ids) and ids[rank] not in seen:
                seen.add(ids[rank])
                pmids.append(ids[rank])
        if len(pmids) >= _PUBMED_CANDIDATE_CAP:
            break
    pmids = pmids[:_PUBMED_CANDIDATE_CAP]

    candidates: list[dict] = []
    if pmids:
        arts = fetch_article_details_impl(pmids, include_abstracts=True)
        for a in arts.get("articles") or []:
            candidates.append(
                {
                    "pmid": str(a.get("pmid") or ""),
                    "title": a.get("title") or "",
                    "authors": a.get("authors") or "",
                    "journal": a.get("source") or "",
                    "year": (str(a.get("pubdate") or "").split() or [""])[0],
                    "abstract": a.get("abstract") or "",  # full abstract — never truncated
                }
            )
    try:
        candidates.extend(_book_candidates(disease_name))
    except Exception as exc:  # noqa: BLE001 — Bookshelf is a bonus channel
        log.debug("guideline_shelf_search: books search failed: %s", exc)
    return candidates
