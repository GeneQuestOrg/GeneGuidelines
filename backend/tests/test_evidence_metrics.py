from __future__ import annotations

import unittest

from backend.evidence_metrics import compute_pubmed_corpus_metrics


class EvidenceMetricsTests(unittest.TestCase):
    def test_metrics_are_deterministic_for_high_quality_corpus(self) -> None:
        articles = [
            {"title": "Systematic review in fibrous dysplasia", "abstract": "clinical trial"},
            {"title": "Randomized controlled trial", "abstract": "treatment"},
        ]
        m = compute_pubmed_corpus_metrics(
            articles,
            total_found_estimate=2,
            total_requested=2,
            fallback_used=False,
        )
        self.assertEqual(m["evidence_level"], "moderate")
        self.assertEqual(m["evidence_score"], 65)
        self.assertEqual(m["confidence_index"], 67)
        self.assertEqual(m["metric_breakdown"]["tier_counts"]["high"], 2)
        self.assertTrue(m["coverage_gap"])

    def test_metrics_penalize_empty_articles_deterministically(self) -> None:
        m = compute_pubmed_corpus_metrics(
            [],
            total_found_estimate=30,
            total_requested=30,
            fallback_used=False,
        )
        self.assertEqual(m["evidence_score"], 0)
        self.assertEqual(m["confidence_index"], 5)
        self.assertEqual(m["evidence_level"], "very_low")

    def test_metrics_include_coverage_gap_and_fallback_penalty(self) -> None:
        articles = [{"title": "Case report", "abstract": ""}]
        m = compute_pubmed_corpus_metrics(
            articles,
            total_found_estimate=40,
            total_requested=20,
            fallback_used=True,
        )
        self.assertEqual(m["evidence_level"], "very_low")
        self.assertEqual(m["evidence_score"], 0)
        self.assertEqual(m["confidence_index"], 2)
        self.assertTrue(m["coverage_gap"])


if __name__ == "__main__":
    unittest.main()
