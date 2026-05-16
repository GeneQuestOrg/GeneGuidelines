"""Load published guideline context for parent pathway flow."""
from __future__ import annotations

from typing import Any

from .base import NodeExecutor, NodeInput, NodeOutput


class ParentPathwayLoadExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "parent_pathway_load"

    async def execute(self, input: NodeInput) -> NodeOutput:
        initial = input.initial_data or input.context.get("initial") or {}
        slug = str(initial.get("disease_slug") or "").strip().lower()
        if not slug:
            return NodeOutput(
                data={
                    "ok": False,
                    "error": "disease_slug missing in flow context — start pathway run from admin with a catalog disease.",
                }
            )
        try:
            from backend.flows.parent_pathway.context import load_pathway_context
        except ImportError:
            from flows.parent_pathway.context import load_pathway_context

        payload = load_pathway_context(slug)
        return NodeOutput(data=payload)
