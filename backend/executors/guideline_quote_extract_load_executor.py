"""Executor for the ``guideline_quote_extract_load`` node — Feature 4 loader.

Feeds the quote-extraction node (``gs-quotes``) the freshly-synthesised paragraphs
plus the abstracts of the shelf documents they cite, so the LLM can — per paragraph
— paraphrase the passage in the cited abstract that backs the claim.

Unlike ``guideline_factcheck_load`` (which reads the *persisted* synthesis from the
DB and re-fetches abstracts from PubMed), this node runs INSIDE the synthesis flow,
between the section nodes and the writer. It therefore reads:

  - the just-written paragraphs from ``context["gs-sec-<id>"]`` (the section outputs),
  - the abstracts already loaded by ``gs-shelf`` (``context["gs-shelf"].shelf_docs``).

That keeps the extraction on exactly the paragraphs this run produced and costs
**zero** extra PubMed calls (the shelf loader already fetched every abstract).
"""
from __future__ import annotations

import logging

from .base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)


class GuidelineQuoteExtractLoadExecutor(NodeExecutor):
    """Build (claims, sources) from the in-run synthesis context for quote extraction."""

    @classmethod
    def node_type(cls) -> str:
        return "guideline_quote_extract_load"

    async def execute(self, input: NodeInput) -> NodeOutput:
        initial = input.initial_data or input.context.get("initial") or {}
        context = input.context or {}
        slug = str(initial.get("disease_slug") or "").strip().lower()
        if not slug:
            return NodeOutput(data={"ok": False, "error": "disease_slug missing in flow context."})

        section_specs = _normalize_section_specs(initial.get("sections"))
        if not section_specs:
            return NodeOutput(data={"ok": False, "error": "no section spec in initial.sections."})

        # Sources: the shelf documents + their already-fetched abstracts (no re-fetch).
        shelf = context.get("gs-shelf") if isinstance(context.get("gs-shelf"), dict) else {}
        shelf_docs = shelf.get("shelf_docs") or []
        sources = []
        pmid_by_doc: dict[str, str] = {}
        for d in shelf_docs:
            if not isinstance(d, dict):
                continue
            doc_id = str(d.get("docId") or "").strip()
            if not doc_id:
                continue
            pmid = str(d.get("pmid") or "").strip()
            if pmid:
                pmid_by_doc[doc_id] = pmid
            sources.append(
                {
                    "docId": doc_id,
                    "pmid": pmid or None,
                    "title": str(d.get("title") or ""),
                    "abstract": str(d.get("abstract") or "").strip(),
                }
            )

        # Claims: the paragraphs each section node produced this run.
        claims = []
        for spec in section_specs:
            sid = spec["id"]
            out = context.get(f"gs-sec-{sid}")
            if not isinstance(out, dict):
                continue
            for para in out.get("paragraphs") or []:
                if not isinstance(para, dict):
                    continue
                src = para.get("source") if isinstance(para.get("source"), dict) else {}
                cited_doc = str(src.get("doc") or "").strip()
                text = str(para.get("text") or "").strip()
                pid = str(para.get("id") or "").strip()
                if not text or not pid:
                    continue
                citations = [str(c).strip() for c in (para.get("citations") or []) if str(c).strip().isdigit()]
                # Surface the docId's own PMID too, so the extractor can attribute even
                # when the section node left `citations` empty but named a PMID-bearing doc.
                doc_pmid = pmid_by_doc.get(cited_doc, "")
                claims.append(
                    {
                        "section_id": sid,
                        "paragraph_id": pid,
                        "text": text,
                        "cited_doc": cited_doc,
                        "cited_pmid": doc_pmid or None,
                        "citations": citations,
                    }
                )

        if not claims:
            return NodeOutput(
                data={"ok": False, "error": "no synthesised paragraphs in context to extract quotes from."}
            )

        return NodeOutput(
            data={
                "ok": True,
                "slug": slug,
                "claims": claims,
                "sources": sources,
                "claim_count": len(claims),
            }
        )


def _normalize_section_specs(raw) -> list[dict]:
    """Coerce ``initial.sections`` into a list of {id} dicts (same rule as the writer)."""
    specs: list[dict] = []
    if not isinstance(raw, list):
        return specs
    for item in raw:
        if isinstance(item, dict) and str(item.get("id") or "").strip():
            specs.append({"id": str(item["id"]).strip()})
        elif isinstance(item, str) and item.strip():
            specs.append({"id": item.strip()})
    return specs
