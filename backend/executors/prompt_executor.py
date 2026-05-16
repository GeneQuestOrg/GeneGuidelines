from __future__ import annotations

from .base import NodeExecutor, NodeInput, NodeOutput


class PromptExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "prompt"

    async def execute(self, input: NodeInput) -> NodeOutput:
        # Flow engine executes prompt logic; executor keeps normalized shape.
        prompt = input.node_config.get("prompt", "")
        return NodeOutput(data={"ok": True, "prompt": prompt})

