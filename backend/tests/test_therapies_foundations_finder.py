"""Therapies and foundations finder resilience (batch + fallback)."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote_plus

from backend.services import foundations_finder as ff
from backend.services import therapies_finder as tf


class _FakeResp:
    """Minimal urlopen context manager returning canned JSON for query-capture tests."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *_a: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


def _capturing_urlopen(captured: list[str], payload: bytes = b'{"esearchresult":{"idlist":[]}}'):
    def _fake(req, timeout=None):  # noqa: ANN001
        captured.append(getattr(req, "full_url", str(req)))
        return _FakeResp(payload)

    return _fake


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


# ── gene-aware therapies search (ultra-rare: name finds ~0 reviews, gene finds them) ──


def test_therapies_pubmed_query_ors_gene(monkeypatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(tf.urllib.request, "urlopen", _capturing_urlopen(captured))
    tf._pubmed_search_review_pmids("Ultra Rare Disease", "PUS3")
    q = unquote_plus(captured[0])
    assert '"PUS3"[Title/Abstract]' in q  # gene OR'd in (Title/Abstract scoped)
    assert '"Ultra Rare Disease"[Title/Abstract]' in q  # disease name kept
    assert " OR " in q  # OR (broaden), not AND (narrow)
    assert "review[Publication Type]" in q.lower() or "review[publication type]" in q.lower()


def test_therapies_pubmed_query_omits_gene_when_absent_or_short(monkeypatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr(tf.urllib.request, "urlopen", _capturing_urlopen(captured))
    tf._pubmed_search_review_pmids("Fibrous Dysplasia")  # no gene
    tf._pubmed_search_review_pmids("Fibrous Dysplasia", "X")  # too short (<3 chars)
    assert "PUS3" not in unquote_plus(captured[0])
    # Disease block is the bare name phrase — no gene OR'd between two Title/Abstract phrases.
    assert '[Title/Abstract] OR "' not in unquote_plus(captured[0])
    assert '"X"[Title/Abstract]' not in unquote_plus(captured[1])


class TherapiesFinderGeneResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_therapies_threads_resolved_gene(self) -> None:
        """Gene is resolved from the disease row and threaded into the PubMed search."""
        seen: dict = {}
        with patch.object(tf, "_resolve_gene_for_slug", return_value="PUS3"):
            with patch.object(
                tf,
                "_pubmed_search_review_pmids",
                side_effect=lambda name, gene=None: seen.update(gene=gene) or [],
            ):
                with patch.object(tf, "_pubmed_fetch_abstracts", return_value=[]):
                    with patch.object(tf, "_log_run"):
                        inserted = await tf.find_therapies_for_disease("some-slug", "Some Disease")
        self.assertEqual(seen["gene"], "PUS3")
        self.assertEqual(inserted, 0)

    async def test_find_therapies_explicit_gene_wins(self) -> None:
        seen: dict = {}
        with patch.object(
            tf,
            "_resolve_gene_for_slug",
            side_effect=AssertionError("row resolver must not run when gene is explicit"),
        ):
            with patch.object(
                tf,
                "_pubmed_search_review_pmids",
                side_effect=lambda name, gene=None: seen.update(gene=gene) or [],
            ):
                with patch.object(tf, "_pubmed_fetch_abstracts", return_value=[]):
                    with patch.object(tf, "_log_run"):
                        await tf.find_therapies_for_disease("s", "N", gene="GNAS")
        self.assertEqual(seen["gene"], "GNAS")


if __name__ == "__main__":
    unittest.main()
