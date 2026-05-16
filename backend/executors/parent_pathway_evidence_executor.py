"""Optional targeted PubMed excerpts for parent pathway flow."""
from __future__ import annotations

from .base import NodeExecutor, NodeInput, NodeOutput


class ParentPathwayEvidenceExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "parent_pathway_evidence"

    async def execute(self, input: NodeInput) -> NodeOutput:
        initial = input.initial_data or {}
        raw_refresh = initial.get("refresh_pubmed")
        refresh = raw_refresh in (True, 1, "1", "true", "True")
        if not refresh:
            return NodeOutput(data={"ok": True, "skipped": True, "articles_text": "", "pmids": []})

        load_out = input.context.get("outputs", {}).get("pp-load", {})
        if isinstance(load_out, dict) and load_out.get("result"):
            load_out = load_out["result"]
        if not isinstance(load_out, dict) or not load_out.get("ok"):
            return NodeOutput(
                data={
                    "ok": False,
                    "error": "pp-load did not succeed — cannot fetch PubMed excerpts.",
                }
            )
        disease_name = str(load_out.get("disease_name") or "")
        try:
            from backend.flows.parent_pathway.context import fetch_optional_pubmed_excerpts
        except ImportError:
            from flows.parent_pathway.context import fetch_optional_pubmed_excerpts

        extra = fetch_optional_pubmed_excerpts(disease_name)
        allowed = list(load_out.get("allowed_pmids") or [])
        for pmid in extra.get("pmids") or []:
            if pmid not in allowed:
                allowed.append(pmid)
        return NodeOutput(
            data={
                **extra,
                "allowed_pmids": allowed,
            }
        )
