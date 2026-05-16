"""Finalize parent pathway flow output from saved chart."""
from __future__ import annotations

from .base import NodeExecutor, NodeInput, NodeOutput


class ParentPathwayEndExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "parent_pathway_end"

    async def execute(self, input: NodeInput) -> NodeOutput:
        initial = input.initial_data or {}
        slug = str(initial.get("disease_slug") or "").strip().lower()
        if not slug:
            return NodeOutput(data={"ok": False, "error": "disease_slug missing in context."})
        try:
            from backend.content_db import get_parent_pathway_draft
        except ImportError:
            from content_db import get_parent_pathway_draft

        saved = get_parent_pathway_draft(slug)
        if saved is None:
            return NodeOutput(
                data={
                    "ok": False,
                    "error": (
                        "Parent pathway draft was not saved. "
                        "Ensure pp-plan completed and pp-synth called submit_parent_pathway successfully, "
                        "then publish from the admin console when ready."
                    ),
                }
            )
        return NodeOutput(
            data={
                "ok": True,
                "pathway": saved,
                "validation_warnings": [],
            }
        )
