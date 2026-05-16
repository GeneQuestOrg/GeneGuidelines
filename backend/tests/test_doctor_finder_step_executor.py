from __future__ import annotations

import asyncio

import pytest

from backend.executors.base import NodeInput
from backend.executors.doctor_finder_step_executor import (
    DoctorFinderStepExecutor,
    _pipeline_base_from_node_outputs,
)


def test_pipeline_base_prefers_latest_node_with_articles() -> None:
    """node_outputs maps node_id → payload; base must be df-1 output, not the whole map."""
    df1 = {"ok": True, "articles": [{"pmid": "1", "authors": []}], "pmids": ["1"], "query_text": '"x"', "total_papers_scanned": 1}
    outputs = {"start": {}, "df-1": df1}
    assert _pipeline_base_from_node_outputs(outputs) == df1


def test_pipeline_base_follows_chain() -> None:
    df2 = {"ok": True, "articles": [{"pmid": "1", "authors": [{"last_name": "A", "affiliations_raw": ["Rome Italy"]}]}]}
    outputs = {"start": {}, "df-1": {"articles": []}, "df-2": df2}
    assert _pipeline_base_from_node_outputs(outputs) == df2


def test_affiliation_parser_sees_articles_from_df1() -> None:
    """Regression: df-2 must read articles from df-1 output, not empty."""
    df1 = {
        "ok": True,
        "articles": [
            {
                "pmid": "123",
                "title": "t",
                "authors": [
                    {
                        "last_name": "Smith",
                        "fore_name": "J",
                        "initials": "J",
                        "affiliations_raw": ["Department of Medicine, Rome, Italy"],
                    }
                ],
            }
        ],
        "pmids": ["123"],
        "query_text": '"test"',
        "total_papers_scanned": 1,
    }
    inp = NodeInput(
        node_config={"step_name": "affiliation_parser", "node_id": "df-2"},
        context={"start": {}, "df-1": df1},
        initial_data={"disease_name": "fibrous dysplasia"},
        flow_runtime=None,
    )
    out = asyncio.run(DoctorFinderStepExecutor().execute(inp))
    assert out.data.get("ok") is True
    arts = out.data.get("articles") or []
    assert len(arts) == 1
    auth0 = (arts[0].get("authors") or [{}])[0]
    assert auth0.get("parsed_affiliation") is not None
