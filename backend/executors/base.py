from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FlowRuntimeBundle:
    """Passed from flow_engine for nodes that need the live store / SSE hooks (e.g. LLM calls)."""

    store: dict[str, Any]
    event_queue: Any
    emit_fn: Any


@dataclass
class NodeInput:
    node_config: dict
    context: dict
    initial_data: dict
    flow_runtime: FlowRuntimeBundle | None = None


@dataclass
class NodeOutput:
    data: dict
    metadata: dict = field(default_factory=dict)
    branch: str | None = None


class NodeExecutor(ABC):
    @abstractmethod
    async def execute(self, input: NodeInput) -> NodeOutput: ...

    @classmethod
    def node_type(cls) -> str: ...
