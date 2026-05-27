from __future__ import annotations

import unittest
from unittest import mock

from backend.flows.pubmed import prompt_context as pc
from backend.engine.flow_engine import _store_for_prompt_interpolation


def _sma_like_articles(count: int = 80) -> list[dict]:
    articles: list[dict] = []
    for i in range(count):
        tier = "guideline" if i < 5 else "review" if i < 20 else "cohort"
        articles.append(
            {
                "pmid": str(30_000_000 + i),
                "title": f"SMA clinical study {i}: nusinersen and risdiplam outcomes",
                "abstract": (
                    "Spinal muscular atrophy motor function and survival were assessed in "
                    "this multicenter cohort. " * 20
                ),
                "topic_bucket": ["diagnostics", "treatment", "follow_up", "general"][i % 4],
                "pubdate": f"{2015 + (i % 10)} Jan",
            }
        )
    cards = [
        {
            "pmid": a["pmid"],
            "topic_bucket": a["topic_bucket"],
            "evidence_tier": "guideline" if int(a["pmid"]) < 30_000_005 else "review",
            "confidence": "high" if int(a["pmid"]) < 30_000_010 else "medium",
            "title": a["title"],
            "pubdate": a["pubdate"],
            "inclusion_reason": "SMA clinical relevance",
        }
        for a in articles
    ]
    return articles, cards


class PubmedPromptContextTests(unittest.TestCase):
    def test_pm3_view_includes_articles_text_not_source_links(self) -> None:
        raw = {
            "result": {
                "query_text": "PKU",
                "article_count": 3,
                "total_analyzed": 3,
                "articles": [
                    {"pmid": "1", "title": "A", "abstract": "alpha"},
                    {"pmid": "2", "title": "B", "abstract": "beta"},
                ],
                "evidence_cards": [{"pmid": "1"}, {"pmid": "2"}],
                "articles_text": "legacy blob",
                "source_links_html": "<ul>" + "<li>x</li>" * 3000 + "</ul>",
            }
        }
        view = pc.pm2_view_for_llm_prompt("pm-3", raw)
        result = view["result"]
        self.assertIn("articles_text", result)
        self.assertIn("PMID: 1", result["articles_text"])
        self.assertNotIn("source_links_html", result)
        self.assertIn("evidence_cards", result)
        self.assertLessEqual(len(result["evidence_cards"][0]), 8)

    def test_pass1_diagnostics_filters_by_topic_bucket(self) -> None:
        raw = {
            "result": {
                "query_text": "PKU",
                "articles": [
                    {"pmid": "1", "title": "Dx", "topic_bucket": "diagnostics", "abstract": "a"},
                    {"pmid": "2", "title": "Tx", "topic_bucket": "treatment", "abstract": "b"},
                ],
                "evidence_cards": [
                    {"pmid": "1", "topic_bucket": "diagnostics"},
                    {"pmid": "2", "topic_bucket": "treatment"},
                ],
                "articles_text": "legacy",
            }
        }
        view = pc.pm2_view_for_llm_prompt("pass1-diagnostics", raw)
        result = view["result"]
        self.assertEqual(result["article_count"], 1)
        self.assertIn("PMID: 1", result["articles_text"])
        self.assertNotIn("PMID: 2", result["articles_text"])
        self.assertEqual(len(result["evidence_cards"]), 1)

    def test_store_interpolation_pm3_does_not_mutate_original_pm2(self) -> None:
        pm2 = {
            "result": {
                "articles_text": "B" * 10_000,
                "query_text": "X",
                "evidence_cards": [],
                "articles": [{"pmid": "1", "title": "T", "abstract": "a"}],
            }
        }
        store = {"node_outputs": {"pm-2": pm2}}
        interp = _store_for_prompt_interpolation("pubmed", "pm-3", store)
        self.assertEqual(len(pm2["result"]["articles_text"]), 10_000)
        self.assertIn("articles_text", interp["node_outputs"]["pm-2"]["result"])
        self.assertIsNot(interp["node_outputs"]["pm-2"], pm2)

    def test_token_budget_caps_pass1_corpus(self) -> None:
        articles = [
            {
                "pmid": str(i),
                "title": f"Paper {i}",
                "abstract": "word " * 400,
                "topic_bucket": "general",
            }
            for i in range(500)
        ]
        raw = {"result": {"query_text": "X", "articles": articles, "evidence_cards": []}}
        with mock.patch.object(pc, "effective_llm_prompt_token_cap", return_value=5_000):
            view = pc.pm2_view_for_llm_prompt("pass1-overview", raw)
        result = view["result"]
        self.assertTrue(result.get("articles_text_corpus_capped"))
        self.assertLess(result["article_count"], 500)

    def test_llm_prompt_token_cap_tightens_pm3_corpus(self) -> None:
        """K6: effective cap must shrink pm-3 below an uncapped TPM ceiling."""
        articles = [
            {
                "pmid": str(i),
                "title": f"Paper {i}",
                "abstract": "word " * 400,
                "topic_bucket": "general",
            }
            for i in range(500)
        ]
        raw = {"result": {"query_text": "Marfan", "articles": articles, "evidence_cards": []}}
        tpm_budget = 380_000

        with mock.patch.object(pc, "effective_llm_prompt_token_cap", return_value=tpm_budget):
            with mock.patch.object(pc, "PUBMED_PM3_TOP_K", 500):
                view_tpm_only = pc.pm2_view_for_llm_prompt("pm-3", raw)
        with mock.patch.object(pc, "effective_llm_prompt_token_cap", return_value=20_000):
            with mock.patch.object(pc, "PUBMED_PM3_TOP_K", 500):
                view_k6 = pc.pm2_view_for_llm_prompt("pm-3", raw)

        tpm_result = view_tpm_only["result"]
        k6_result = view_k6["result"]
        self.assertGreater(tpm_result["article_count"], k6_result["article_count"])
        self.assertTrue(k6_result.get("articles_text_corpus_capped"))
        self.assertLess(
            pc.estimated_pm2_prompt_tokens(view_k6),
            pc.estimated_pm2_prompt_tokens(view_tpm_only),
        )
        self.assertLess(pc.estimated_pm2_prompt_tokens(view_k6), 220_000)
        self.assertLess(pc.estimated_pm2_prompt_tokens(view_k6), 25_000)

    def test_ranking_prefers_guideline_tier_in_pm3(self) -> None:
        raw = {
            "result": {
                "query_text": "SMA",
                "articles": [
                    {"pmid": "1", "title": "Low", "abstract": "a", "pubdate": "2010"},
                    {"pmid": "2", "title": "High", "abstract": "b", "pubdate": "2024"},
                ],
                "evidence_cards": [
                    {"pmid": "1", "evidence_tier": "case_report", "confidence": "low"},
                    {"pmid": "2", "evidence_tier": "guideline", "confidence": "high"},
                ],
            }
        }
        with mock.patch.object(pc, "PUBMED_PM3_TOP_K", 1):
            view = pc.pm2_view_for_llm_prompt("pm-3", raw)
        result = view["result"]
        self.assertEqual(result["article_count"], 1)
        self.assertIn("PMID: 2", result["articles_text"])

    def test_sma_like_corpus_fits_vllm_budget(self) -> None:
        articles, cards = _sma_like_articles(80)
        raw = {
            "result": {
                "query_text": "Spinal Muscular Atrophy",
                "total_analyzed": 80,
                "articles": articles,
                "evidence_cards": cards,
            }
        }
        with mock.patch.object(pc, "effective_llm_prompt_token_cap", return_value=60_000):
            view = pc.pm2_view_for_llm_prompt("pm-3", raw)
        tokens = pc.estimated_pm2_prompt_tokens(view)
        result = view["result"]
        self.assertLessEqual(tokens, 60_000)
        self.assertLessEqual(result["article_count"], pc.PUBMED_PM3_TOP_K)
        self.assertGreater(result["article_count"], 0)


if __name__ == "__main__":
    unittest.main()
