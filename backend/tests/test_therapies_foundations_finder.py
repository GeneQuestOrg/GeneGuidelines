"""Therapies and foundations finder resilience (batch + fallback)."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from backend.services import foundations_finder as ff
from backend.services import therapies_finder as tf


class TherapiesFinderFallbackTests(unittest.TestCase):
    def test_fallback_therapies_from_abstracts(self) -> None:
        abstracts = [
            (
                "41350238",
                "Effectiveness and Safety of Nusinersen and Risdiplam in Spinal Muscular Atrophy\n\n"
                "Both agents improved motor outcomes in treated cohorts.",
            )
        ]
        therapies = tf._fallback_therapies_from_abstracts(abstracts)
        self.assertEqual(len(therapies), 1)
        self.assertEqual(therapies[0].status, "pending")
        self.assertIn("Nusinersen", therapies[0].name)


class FoundationsFinderFallbackTests(unittest.TestCase):
    def test_fallback_foundations_includes_orphanet_link(self) -> None:
        foundations = ff._fallback_foundations(
            "Spinal Muscular Atrophy",
            orphanet_id="ORPHA:70",
        )
        self.assertGreaterEqual(len(foundations), 1)
        self.assertIn("/detail/70", foundations[0].url)
        self.assertGreaterEqual(foundations[0].confidence, 0.6)


class TherapiesFinderFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_therapies_persists_fallback_on_timeout(self) -> None:
        abstracts = [("1", "Drug review title\n\nAbstract text.")]
        with patch.object(tf, "_pubmed_search_review_pmids", return_value=["1"]):
            with patch.object(tf, "_pubmed_fetch_abstracts", return_value=abstracts):
                with patch.object(
                    tf,
                    "_extract_with_gemma",
                    side_effect=asyncio.TimeoutError(),
                ):
                    with patch.object(tf, "_persist_therapies", return_value=1) as mock_persist:
                        with patch.object(tf, "_log_run") as mock_log:
                            inserted = await tf.find_therapies_for_disease(
                                "spinal-muscular-atrophy",
                                "Spinal Muscular Atrophy",
                                execution_id="trp-test-fallback",
                            )
        self.assertEqual(inserted, 1)
        mock_persist.assert_called_once()
        mock_log.assert_called()
        self.assertEqual(mock_log.call_args[0][2], "ready")


class FoundationsFinderFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_foundations_persists_directory_fallback_on_timeout(self) -> None:
        with patch.object(ff, "_lookup_orphanet_id", return_value="ORPHA:70"):
            with patch.object(
                ff,
                "run_structured_with_ollama_fallback",
                side_effect=asyncio.TimeoutError(),
            ):
                with patch.object(ff, "_persist_foundations", return_value=2) as mock_persist:
                    with patch.object(ff, "_log_run") as mock_log:
                        inserted = await ff.find_foundations_for_disease(
                            "spinal-muscular-atrophy",
                            "Spinal Muscular Atrophy",
                            execution_id="fdn-test-fallback",
                        )
        self.assertEqual(inserted, 2)
        mock_persist.assert_called_once()
        persisted = mock_persist.call_args[0][1]
        self.assertGreaterEqual(len(persisted), 1)
        self.assertEqual(mock_log.call_args[0][2], "ready")


if __name__ == "__main__":
    unittest.main()
