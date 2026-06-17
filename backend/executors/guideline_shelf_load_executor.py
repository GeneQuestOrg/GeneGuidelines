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

from .base import NodeExecutor, NodeInput, NodeOutput

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

        shelf_docs = []
        for d in docs:
            pmid = str(getattr(d, "pmid", "") or "").strip() or None
            shelf_docs.append(
                {
                    "docId": d.doc_id,
                    "role": d.role,
                    "pmid": pmid,
                    "bookshelf": getattr(d, "bookshelf", None),
                    "title": d.title,
                    "scope": d.scope,
                    "covers": list(getattr(d, "covers", []) or []),
                    "abstract": abstract_by_pmid.get(pmid or "", ""),
                }
            )

        return NodeOutput(
            data={
                "ok": True,
                "slug": slug,
                "shelf_docs": shelf_docs,
                "shelf_pmids": pmids,
                "abstracts_fetched": sum(1 for v in abstract_by_pmid.values() if v),
            }
        )

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
