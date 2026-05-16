"""Tests for pmid_verifier flow logic and executor."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.executors.base import NodeInput
from backend.executors.pmid_verifier_executor import PmidVerifierExecutor
from backend.flows.pubmed.pmid_verifier import (
    PMID_SUSPICIOUS_THRESHOLD,
    classify_pmids,
    extract_pmids_from_text,
)


class TestExtractPmidsFromText(unittest.TestCase):
    def test_finds_pmid_prefix(self):
        text = "See PMID 31196103 for details."
        result = extract_pmids_from_text(text)
        assert "31196103" in result

    def test_finds_pmid_colon_prefix(self):
        text = "Reference: PMID:33276154"
        result = extract_pmids_from_text(text)
        assert "33276154" in result

    def test_finds_bare_numbers(self):
        text = "As shown in (31196103), the treatment..."
        result = extract_pmids_from_text(text)
        assert "31196103" in result

    def test_ignores_short_numbers(self):
        text = "There were 1234 patients in 56789 studies."
        result = extract_pmids_from_text(text)
        assert "1234" not in result
        assert "56789" not in result

    def test_returns_unique_ordered(self):
        text = "PMID 31196103 and PMID 31196103 again, plus 33276154"
        result = extract_pmids_from_text(text)
        assert result.count("31196103") == 1
        assert "33276154" in result


class TestClassifyPmids(unittest.TestCase):
    def test_in_retrieved(self):
        retrieved = {"31196103", "33276154"}
        result = classify_pmids(["31196103"], retrieved)
        assert "31196103" in result["in_retrieved"]
        assert result["unverified"] == []
        assert result["suspicious"] == []

    def test_suspicious_above_threshold(self):
        retrieved: set[str] = set()
        result = classify_pmids([str(PMID_SUSPICIOUS_THRESHOLD + 1)], retrieved)
        assert str(PMID_SUSPICIOUS_THRESHOLD + 1) in result["suspicious"]
        assert result["unverified"] == []

    def test_unverified_below_threshold_not_in_retrieved(self):
        retrieved: set[str] = set()
        result = classify_pmids(["31196103"], retrieved)
        assert "31196103" in result["unverified"]
        assert result["suspicious"] == []

    def test_mixed_classification(self):
        retrieved = {"31196103"}
        suspicious_pmid = str(PMID_SUSPICIOUS_THRESHOLD + 100)
        cited = ["31196103", "33276154", suspicious_pmid]
        result = classify_pmids(cited, retrieved)
        assert "31196103" in result["in_retrieved"]
        assert "33276154" in result["unverified"]
        assert suspicious_pmid in result["suspicious"]


class TestPmidVerifierExecutor(unittest.IsolatedAsyncioTestCase):
    async def test_integration_verifies_pmids(self):
        """Integration test: mock fetch_article_details_impl, verify output structure.

        PMID 38174586 is below PMID_SUSPICIOUS_THRESHOLD (41_500_000) and not in the retrieved set,
        so it is classified as 'unverified' and sent to esummary for confirmation.
        """
        store = {
            "pm-1": {
                "result": {
                    "unique_pmids": ["31196103", "33276154", "35104665"],
                }
            },
            "pm-5": {
                # 38174586 is below threshold and not in pm-1 → goes to esummary
                "output_text": "See PMID 31196103 for overview. Also PMID 33276154 and PMID 38174586.",
            },
        }

        mock_esummary_return = {
            "articles": [{"pmid": "38174586", "title": "Danish registry 2024"}],
            "evidence_cards": [],
        }

        async def fake_run_in_executor(_exc, fn):
            return mock_esummary_return

        with patch("backend.executors.pmid_verifier_executor.asyncio.get_event_loop") as mock_loop:
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop
            mock_event_loop.run_in_executor = fake_run_in_executor

            executor = PmidVerifierExecutor()
            node_input = NodeInput(node_config={}, context=store, initial_data={})
            result = await executor.execute(node_input)

        data = result.data
        assert data["ok"] is True
        assert data["total_cited"] == 3
        assert "31196103" in data["in_retrieved_set"]
        assert "33276154" in data["in_retrieved_set"]
        assert "38174586" in data["confirmed_by_esummary"]
        assert data["verification_rate"] == 1.0
        assert "3/3" in data["summary"]

    async def test_no_pmids_returns_ok_with_rate_1(self):
        """When synthesis has no PMIDs, returns ok=True with rate 1.0."""
        store = {
            "pm-5": {"output_text": "No citations in this text."},
            "pm-1": {"result": {"unique_pmids": []}},
        }
        executor = PmidVerifierExecutor()
        node_input = NodeInput(node_config={}, context=store, initial_data={})
        result = await executor.execute(node_input)
        assert result.data["ok"] is True
        assert result.data["total_cited"] == 0
        assert result.data["verification_rate"] == 1.0
