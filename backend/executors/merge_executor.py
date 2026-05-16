from __future__ import annotations

from .base import NodeExecutor, NodeInput, NodeOutput


class MergeExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "merge"

    async def execute(self, input: NodeInput) -> NodeOutput:
        # Actual merge strategy is handled in flow_engine.
        strategy = (input.node_config.get("merge_strategy") or "append").strip().lower()
        return NodeOutput(data={"ok": True, "strategy": strategy})

