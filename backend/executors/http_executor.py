from __future__ import annotations

from .http_request_runner import run_http_request_async
from .base import NodeExecutor, NodeInput, NodeOutput


class HttpExecutor(NodeExecutor):
    @classmethod
    def node_type(cls) -> str:
        return "http"

    async def execute(self, input: NodeInput) -> NodeOutput:
        out = await run_http_request_async(
            url=str(input.node_config.get("http_url") or ""),
            method=str(input.node_config.get("http_method") or "GET"),
            headers=input.node_config.get("http_headers_json") or {},
            body=input.node_config.get("http_body_template") or "",
        )
        return NodeOutput(data=out)

