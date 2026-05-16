"""Tests for guidelines_rag flow logic and executor."""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from backend.executors.base import NodeInput
from backend.executors.guidelines_rag_executor import GuidelinesRagExecutor, _resolve_anchor_pmids
from backend.flows.pubmed.guidelines_rag import DEFAULT_ANCHOR_PMIDS, build_consensus_context


class TestBuildConsensusContext(unittest.TestCase):
    def test_empty_returns_empty_string(self):
        assert build_consensus_context([]) == ""

    def test_formats_articles(self):
        articles = [
            {
                "pmid": "31196103",
                "title": "Fibrous Dysplasia Consensus",
                "authors": "Javaid MK et al.",
                "pubdate": "2019",
                "abstract": "A consensus statement...",
            }
        ]
        result = build_consensus_context(articles)
        assert "CONSENSUS REFERENCE CONTEXT" in result
        assert "PMID 31196103" in result
        assert "Javaid MK et al." in result
        assert "A consensus statement" in result

    def test_no_abstract_omits_abstract_line(self):
        articles = [{"pmid": "12345678", "title": "Test", "authors": "Author", "pubdate": "2020", "abstract": ""}]
        result = build_consensus_context(articles)
        assert "PMID 12345678" in result
        assert "Abstract:" not in result


class TestResolveAnchorPmids(unittest.TestCase):
    def test_uses_node_config(self):
        node_config = {"guidelines_rag_anchor_pmids_json": json.dumps(["11111111", "22222222"])}
        result = _resolve_anchor_pmids(node_config)
        assert result == ["11111111", "22222222"]

    def test_uses_defaults_when_empty_config(self):
        result = _resolve_anchor_pmids({})
        assert result == DEFAULT_ANCHOR_PMIDS

    def test_ignores_invalid_json_falls_through_to_defaults(self):
        node_config = {"guidelines_rag_anchor_pmids_json": "not-valid-json"}
        result = _resolve_anchor_pmids(node_config)
        assert result == DEFAULT_ANCHOR_PMIDS


class TestGuidelinesRagExecutor(unittest.IsolatedAsyncioTestCase):
    async def test_no_anchor_pmids_returns_ok_true_empty(self):
        """When anchor_pmids resolves to empty list, returns ok=True with empty articles."""
        executor = GuidelinesRagExecutor()
        node_input = NodeInput(
            node_config={"guidelines_rag_anchor_pmids_json": "[]"},
            context={},
            initial_data={},
        )
        result = await executor.execute(node_input)
        assert result.data["ok"] is True
        assert result.data["anchor_pmids_fetched"] == 0
        assert result.data["articles"] == []
        assert result.data["consensus_context"] == ""

    async def test_uses_default_anchor_pmids(self):
        """When no config override, executor uses DEFAULT_ANCHOR_PMIDS and returns results."""
        mock_return = {
            "articles": [
                {"pmid": "31196103", "title": "Test", "authors": "A", "pubdate": "2019", "abstract": "Abstract text"}
            ],
            "evidence_cards": [],
        }

        async def fake_run_in_executor(_exc, fn):
            return mock_return

        with patch("backend.executors.guidelines_rag_executor.asyncio.get_event_loop") as mock_loop:
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop
            mock_event_loop.run_in_executor = fake_run_in_executor

            executor = GuidelinesRagExecutor()
            node_input = NodeInput(node_config={}, context={}, initial_data={})
            result = await executor.execute(node_input)

        assert result.data["ok"] is True
        assert result.data["anchor_pmids_fetched"] == 1

    async def test_graceful_on_pubmed_error(self):
        """On PubMed error, executor returns ok=False but does not raise."""

        async def failing_run_in_executor(_exc, fn):
            raise RuntimeError("Network error")

        with patch("backend.executors.guidelines_rag_executor.asyncio.get_event_loop") as mock_loop:
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop
            mock_event_loop.run_in_executor = failing_run_in_executor

            executor = GuidelinesRagExecutor()
            node_input = NodeInput(node_config={}, context={}, initial_data={})
            result = await executor.execute(node_input)

        assert result.data["ok"] is False
        assert "error" in result.data
