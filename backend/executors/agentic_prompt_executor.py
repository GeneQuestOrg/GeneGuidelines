from __future__ import annotations

from .base import NodeExecutor, NodeInput, NodeOutput


class AgenticPromptExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "agentic_prompt"

    async def execute(self, input: NodeInput) -> NodeOutput:
        prompt = input.node_config.get("prompt", "")
        return NodeOutput(data={"ok": True, "prompt": prompt, "mode": "agentic"})

