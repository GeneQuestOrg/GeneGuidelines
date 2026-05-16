"""Executor for guidelines_rag node — fetches consensus anchor abstracts."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)


class GuidelinesRagExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "guidelines_rag"

    async def execute(self, input: NodeInput) -> NodeOutput:
        from backend.flows.pubmed.guidelines_rag import build_consensus_context
        from backend.tools.pubmed_runtime import fetch_article_details_impl

        anchor_pmids = _resolve_anchor_pmids(input.node_config)

        if not anchor_pmids:
            return NodeOutput(data={
                "ok": True,
                "consensus_context": "",
                "anchor_pmids_fetched": 0,
                "articles": [],
            })

        try:
            loop = asyncio.get_event_loop()
            raw = await loop.run_in_executor(
                None,
                lambda: fetch_article_details_impl(anchor_pmids, include_abstracts=True),
            )
            articles: list[dict[str, Any]] = raw.get("articles") or []
            consensus_context = build_consensus_context(articles)
            return NodeOutput(data={
                "ok": True,
                "consensus_context": consensus_context,
                "anchor_pmids_fetched": len(articles),
                "articles": articles,
            })
        except Exception as exc:
            log.warning("GuidelinesRagExecutor: PubMed fetch failed: %s", exc)
            return NodeOutput(data={
                "ok": False,
                "error": str(exc),
                "consensus_context": "",
                "anchor_pmids_fetched": 0,
                "articles": [],
            })


def _resolve_anchor_pmids(node_config: dict) -> list[str]:
    """Return anchor PMIDs from node config, env config, or DEFAULT_ANCHOR_PMIDS."""
    from backend.flows.pubmed.guidelines_rag import DEFAULT_ANCHOR_PMIDS
    from backend import config as config_mod

    # 1. Node-level override (stored in DB column guidelines_rag_anchor_pmids_json)
    raw_json = (node_config.get("guidelines_rag_anchor_pmids_json") or "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list) and all(isinstance(p, str) for p in parsed):
                return [p.strip() for p in parsed if p.strip()]
        except (json.JSONDecodeError, TypeError):
            log.warning("GuidelinesRagExecutor: invalid guidelines_rag_anchor_pmids_json, ignoring")

    # 2. Env-level override
    env_pmids: list[str] = getattr(config_mod, "GUIDELINES_RAG_ANCHOR_PMIDS", [])
    if env_pmids:
        return env_pmids

    # 3. Code defaults
    return DEFAULT_ANCHOR_PMIDS
