from __future__ import annotations

from typing import Any

from ..executors import EXECUTOR_REGISTRY


def get_executor_registry() -> dict[str, Any]:
    return EXECUTOR_REGISTRY


def get_executor_for_node_type(node_type: str) -> Any:
    return EXECUTOR_REGISTRY.get((node_type or "").strip().lower())

