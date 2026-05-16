from __future__ import annotations

import json
import unittest

from backend.flow_pm2_normalize import run


class FlowPm2NormalizeTests(unittest.TestCase):
    def test_run_handles_wrapped_result_shape(self) -> None:
        payload = {
            "ok": True,
            "result": {
                "query_text": "fibrous dysplasia",
                "total_found_estimate": 50,
                "total_requested": 50,
                "articles": [{"pmid": "1", "title": "Treatment trial", "abstract": "Randomized controlled trial"}],
                "evidence_cards": [{"pmid": "1", "topic_bucket": "treatment"}],
            },
        }
        ctx = {"outputs": {"pm-1": {"output_text": json.dumps(payload)}}, "initial": {"title": "T"}}
        out = run(ctx)
        self.assertEqual(out["article_count"], 1)
        self.assertTrue(out["contract_mismatch_detected"])
        self.assertIn("field_from_result.articles", out["normalization_notes"])

    def test_run_handles_wrapped_results_shape(self) -> None:
        payload = {
            "ok": True,
            "results": {
                "query_text": "fibrous dysplasia",
                "total_found_estimate": 21,
                "total_requested": 21,
                "articles": [{"pmid": "21", "title": "Diagnostics cohort", "abstract": "Imaging based diagnosis"}],
                "evidence_cards": [{"pmid": "21", "topic_bucket": "diagnostics"}],
            },
        }
        ctx = {"outputs": {"pm-1": {"output_text": json.dumps(payload)}}, "initial": {"title": "T"}}
        out = run(ctx)
        self.assertEqual(out["article_count"], 1)
        self.assertTrue(out["contract_mismatch_detected"])
        self.assertIn("field_from_results.articles", out["normalization_notes"])

    def test_run_sets_retrieval_failure_reason(self) -> None:
        payload = {"query_text": "x", "total_found_estimate": 20, "total_requested": 20, "articles": [], "evidence_cards": []}
        ctx = {"outputs": {"pm-1": {"output_text": json.dumps(payload)}}, "initial": {"title": "T"}}
        out = run(ctx)
        self.assertFalse(out["retrieval_ok"])
        self.assertIn("no_articles_after_normalization", out["retrieval_failure_reason"])

    def test_run_salvages_json_wrapped_in_text(self) -> None:
        payload = {
            "query_text": "fibrous dysplasia",
            "total_found_estimate": 1,
            "total_requested": 1,
            "articles": [{"pmid": "11", "title": "Systematic review", "abstract": "A"}],
            "evidence_cards": [],
        }
        noisy = f"debug-prefix::{json.dumps(payload)}::debug-suffix"
        out = run({"outputs": {"pm-1": {"output_text": noisy}}, "initial": {"title": "T"}})
        self.assertEqual(out["article_count"], 1)
        self.assertEqual(out["articles"][0]["pmid"], "11")

    def test_run_deduplicates_articles_by_pmid_prefering_richer_record(self) -> None:
        payload = {
            "query_text": "fibrous dysplasia",
            "total_found_estimate": 2,
            "total_requested": 2,
            "articles": [
                {"pmid": "77", "title": "Short", "abstract": "", "pubdate": "2024"},
                {"pmid": "77", "title": "Detailed title", "abstract": "Detailed abstract", "pubdate": "2025"},
            ],
            "evidence_cards": [],
        }
        out = run({"outputs": {"pm-1": {"output_text": json.dumps(payload)}}, "initial": {"title": "T"}})
        self.assertEqual(out["article_count"], 1)
        self.assertEqual(out["articles"][0]["pmid"], "77")
        self.assertEqual(out["articles"][0]["title"], "Detailed title")
        self.assertEqual(out["total_with_abstract"], 1)

    def test_run_maps_unknown_topic_bucket_to_general(self) -> None:
        payload = {
            "query_text": "fibrous dysplasia",
            "total_found_estimate": 1,
            "total_requested": 1,
            "articles": [{"pmid": "99", "title": "Trial", "abstract": "A"}],
            "evidence_cards": [{"pmid": "99", "topic_bucket": "unknown_bucket"}],
        }
        out = run({"outputs": {"pm-1": {"output_text": json.dumps(payload)}}, "initial": {"title": "T"}})
        self.assertEqual(out["topic_bucket_counts"]["general"], 1)
        self.assertEqual(out["topic_bucket_counts"]["diagnostics"], 0)

    def test_run_maps_id_field_to_pmid(self) -> None:
        payload = {
            "query_text": "fibrous dysplasia",
            "articles": [{"id": "404", "title": "Case report", "abstract": "A"}],
            "evidence_cards": [{"id": "404", "topic_bucket": "general"}],
        }
        out = run({"outputs": {"pm-1": {"output_text": json.dumps(payload)}}, "initial": {"title": "T"}})
        self.assertEqual(out["article_count"], 1)
        self.assertEqual(out["articles"][0]["pmid"], "404")
        self.assertEqual(out["evidence_cards"][0]["pmid"], "404")


if __name__ == "__main__":
    unittest.main()
