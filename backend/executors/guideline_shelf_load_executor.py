"""Executor for the ``guideline_shelf_load`` node — the synthesis flow's entry.

Loads a disease's curated source shelf (GL-4 ``guideline_source_documents``) and,
for the documents that carry a PMID, fetches the abstract from PubMed. The output
is the *input* to the section-synthesis nodes (the prose they synthesise from) and
the *authoritative* set of doc-ids / PMIDs the anti-hallucination backbone checks
citations against.

Reads ``disease_slug`` from the flow's initial context. PubMed failure is soft:
the shelf is still returned (with empty abstracts) so synthesis is never blocked by
a transient E-utilities outage.
"""
from __future__ import annotations

import asyncio
import logging

from ..config import NCBI_API_KEY
from ..tools.pmc_fulltext import pmc_url
from .base import NodeExecutor, NodeInput, NodeOutput

# Per-document character budget for open-access full text.
#
# Measured on the FD shelf: the whole shelf at full length is ~79k chars ≈ 20k
# tokens, i.e. 10% of LLM_PROMPT_TOKEN_CAP (200k). The old 40k cap was set from a
# guess and was throwing away 36% of the consensus document for no reason. 120k
# per document keeps every realistic guideline whole while still bounding a
# pathological outlier, and a five-document shelf at that ceiling would still be
# ~150k tokens — inside the cap, though the cap is the real backstop, not this.
_FULLTEXT_CHARS_PER_DOC = 120_000

log = logging.getLogger(__name__)


class GuidelineShelfLoadExecutor(NodeExecutor):
    """Load the source shelf + abstracts for the disease under synthesis."""

    def __init__(self, repo=None) -> None:
        # ``repo`` is injectable for tests; production instantiation (via the
        # EXECUTOR_REGISTRY) passes nothing and we build the SQLA repo lazily.
        self._repo = repo

    @classmethod
    def node_type(cls) -> str:
        return "guideline_shelf_load"

    def _get_repo(self):
        if self._repo is not None:
            return self._repo
        from ..guidelines.repository import SqlaGuidelinesRepo

        return SqlaGuidelinesRepo()

    async def execute(self, input: NodeInput) -> NodeOutput:
        initial = input.initial_data or input.context.get("initial") or {}
        slug = str(initial.get("disease_slug") or "").strip().lower()
        if not slug:
            return NodeOutput(
                data={
                    "ok": False,
                    "error": "disease_slug missing in flow context — start the synthesis run for a catalog disease.",
                }
            )

        loop = asyncio.get_event_loop()
        try:
            docs = await loop.run_in_executor(
                None, lambda: self._get_repo().list_source_documents(slug)
            )
        except Exception as exc:  # noqa: BLE001 — a DB error here must surface, not silently pass
            log.warning("guideline_shelf_load: repo read failed for %s: %s", slug, exc)
            return NodeOutput(data={"ok": False, "error": f"shelf read failed: {exc}"})

        if not docs:
            return NodeOutput(
                data={
                    "ok": False,
                    "error": f"No source shelf for '{slug}' — seed guideline_source_documents before synthesis.",
                    "shelf_docs": [],
                    "shelf_pmids": [],
                }
            )

        pmids = [str(d.pmid).strip() for d in docs if str(getattr(d, "pmid", "") or "").strip()]
        abstract_by_pmid = await self._fetch_abstracts(pmids)
        fulltext_by_pmid, pmcid_by_pmid = await self._fetch_fulltexts(pmids)

        shelf_docs = []
        for d in docs:
            pmid = str(getattr(d, "pmid", "") or "").strip() or None
            key = pmid or ""
            fulltext = fulltext_by_pmid.get(key, "")
            pmcid = pmcid_by_pmid.get(key)
            shelf_docs.append(
                {
                    "docId": d.doc_id,
                    "role": d.role,
                    "pmid": pmid,
                    "pmcid": pmcid,
                    "fullTextUrl": pmc_url(pmcid) if pmcid else None,
                    "bookshelf": getattr(d, "bookshelf", None),
                    "title": d.title,
                    "scope": d.scope,
                    "covers": list(getattr(d, "covers", []) or []),
                    "abstract": abstract_by_pmid.get(key, ""),
                    # The section-tagged open-access body when we have it, so the
                    # section prompts can quote actual recommendations instead of
                    # paraphrasing an abstract. Empty string = abstract only.
                    "fullText": fulltext,
                    "textSource": "full-text" if fulltext else "abstract",
                }
            )

        return NodeOutput(
            data={
                "ok": True,
                "slug": slug,
                "shelf_docs": shelf_docs,
                "shelf_pmids": pmids,
                "abstracts_fetched": sum(1 for v in abstract_by_pmid.values() if v),
                "fulltexts_fetched": sum(1 for v in fulltext_by_pmid.values() if v),
            }
        )

    async def _fetch_fulltexts(
        self, pmids: list[str]
    ) -> tuple[dict[str, str], dict[str, str]]:
        """(PMID → prompt-ready full text, PMID → PMCID). Soft-fails to ({}, {}).

        Only open-access articles have a body to fetch; the rest keep serving their
        abstract, which is what every synthesis ran on before this. The per-article
        character budget keeps a five-document shelf inside LLM_PROMPT_TOKEN_CAP
        even when every document resolves.
        """
        if not pmids:
            return {}, {}
        from ..tools.pmc_fulltext import _pmid_to_pmcid, fetch_fulltext_by_pmid

        loop = asyncio.get_event_loop()
        try:
            fulltexts = await loop.run_in_executor(
                None,
                lambda: fetch_fulltext_by_pmid(
                    pmids, char_budget=_FULLTEXT_CHARS_PER_DOC, api_key=NCBI_API_KEY or None
                ),
            )
            pmcids = await loop.run_in_executor(
                None, lambda: _pmid_to_pmcid(pmids, api_key=NCBI_API_KEY or None)
            )
        except Exception as exc:  # noqa: BLE001 — an upgrade, never a dependency
            log.warning("guideline_shelf_load: full-text fetch failed: %s", exc)
            return {}, {}
        log.info(
            "guideline_shelf_load: full text for %d/%d shelf documents",
            sum(1 for v in fulltexts.values() if v),
            len(pmids),
        )
        return fulltexts, pmcids

    async def _fetch_abstracts(self, pmids: list[str]) -> dict[str, str]:
        """PMID → abstract map via PubMed esummary/efetch. Soft-fails to {}."""
        if not pmids:
            return {}
        # Imported lazily so tests can monkeypatch the non-MCP impl.
        from ..tools.pubmed_runtime import fetch_article_details_impl

        loop = asyncio.get_event_loop()
        try:
            raw = await loop.run_in_executor(
                None, lambda: fetch_article_details_impl(pmids, include_abstracts=True)
            )
        except Exception as exc:  # noqa: BLE001 — abstracts are best-effort, never block synthesis
            log.warning("guideline_shelf_load: abstract fetch failed: %s", exc)
            return {}
        out: dict[str, str] = {}
        for art in raw.get("articles") or []:
            pmid = str(art.get("pmid") or "").strip()
            if pmid:
                out[pmid] = str(art.get("abstract") or "").strip()
        return out
