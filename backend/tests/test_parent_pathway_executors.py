"""Unit tests for parent pathway flow executors."""
from __future__ import annotations

import asyncio

from backend.executors.base import NodeInput
from backend.executors.parent_pathway_end_executor import ParentPathwayEndExecutor
from backend.executors.parent_pathway_load_executor import ParentPathwayLoadExecutor


def test_parent_pathway_load_missing_slug() -> None:
    executor = ParentPathwayLoadExecutor()
    out = asyncio.run(executor.execute(NodeInput(node_config={}, context={}, initial_data={})))
    assert out.data.get("ok") is False
    assert "disease_slug" in str(out.data.get("error") or "").lower()


def test_parent_pathway_end_missing_slug() -> None:
    executor = ParentPathwayEndExecutor()
    out = asyncio.run(executor.execute(NodeInput(node_config={}, context={}, initial_data={})))
    assert out.data.get("ok") is False
    assert "disease_slug" in str(out.data.get("error") or "").lower()
