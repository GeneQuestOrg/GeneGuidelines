from __future__ import annotations

import unittest
from unittest import mock

from backend.flows.pubmed import prompt_context as pc
from backend.engine.flow_engine import _store_for_prompt_interpolation


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
        with mock.patch.object(pc, "OPENAI_TPM_REQUEST_TOKEN_BUDGET", 5_000):
            view = pc.pm2_view_for_llm_prompt("pass1-overview", raw)
        result = view["result"]
        self.assertTrue(result.get("articles_text_corpus_capped"))
        self.assertLess(result["article_count"], 500)


if __name__ == "__main__":
    unittest.main()
