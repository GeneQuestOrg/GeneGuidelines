from __future__ import annotations

from .base import NodeExecutor, NodeInput, NodeOutput


class ApprovalExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "approval"

    async def execute(self, input: NodeInput) -> NodeOutput:
        return NodeOutput(data={"ok": True, "requires_approval": True})

