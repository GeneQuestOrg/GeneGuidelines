from __future__ import annotations

from .code_node_runner import run_code_node_async
from .base import NodeExecutor, NodeInput, NodeOutput


class CodeExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "code"

    async def execute(self, input: NodeInput) -> NodeOutput:
        out = await run_code_node_async(
            python_source=str(input.node_config.get("python_source") or ""),
            context=input.context,
        )
        return NodeOutput(data=out)

