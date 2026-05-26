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
        with mock.patch.object(pc, "prompt_input_token_budget", return_value=5_000):
            view = pc.pm2_view_for_llm_prompt("pass1-overview", raw)
        result = view["result"]
        self.assertTrue(result.get("articles_text_corpus_capped"))
        self.assertLess(result["article_count"], 500)

    def test_pm3_large_evidence_manifest_reduces_corpus_budget(self) -> None:
        """Large evidence_manifest must not crowd out the corpus token budget."""
        large_manifest = [{"pmid": str(i), "tier": "T1", "score": 5, "details": "x" * 200} for i in range(200)]
        articles = [{"pmid": str(i), "title": f"Article {i}", "abstract": "a" * 1000} for i in range(50)]
        raw = {
            "result": {
                "query_text": "PKU",
                "article_count": 50,
                "total_analyzed": 50,
                "evidence_manifest": large_manifest,
                "articles": articles,
                "evidence_cards": [{"pmid": str(i)} for i in range(50)],
                "articles_text": "legacy",
            }
        }
        model_spec = "openrouter:google/gemma-4-31B-it"  # 262144 context window
        view = pc.pm2_view_for_llm_prompt("pm-3", raw, model_spec=model_spec)
        result = view["result"]
        # Total estimated tokens should not exceed the model's context limit (262144)
        import json
        total_text = json.dumps(result, ensure_ascii=False, default=str)
        estimated_total = max(1, len(total_text) // 4)
        self.assertLess(estimated_total, 262_144 - 12_000,
            f"pm-3 payload too large: ~{estimated_total} estimated tokens")
        self.assertIn("articles_text", result)

    def test_pm3_respects_gemma_context_ceiling(self) -> None:
        from backend.agents.llm_limits import prompt_input_token_budget

        spec = "openrouter:google/gemma-4-31B-it"
        budget = prompt_input_token_budget(spec)
        self.assertLessEqual(budget, 262_144 - 12_000)
        articles = [
            {
                "pmid": str(i),
                "title": f"Paper {i}",
                "abstract": "word " * 500,
                "topic_bucket": "general",
            }
            for i in range(800)
        ]
        raw = {
            "result": {
                "query_text": "Marfan syndrome",
                "articles": articles,
                "evidence_cards": [{"pmid": str(i)} for i in range(800)],
            }
        }
        view = pc.pm2_view_for_llm_prompt("pm-3", raw, model_spec=spec)
        tokens = pc.estimated_pm2_prompt_tokens(view)
        self.assertLess(tokens, 262_144, f"pm-3 view still ~{tokens} tokens for gemma")


if __name__ == "__main__":
    unittest.main()
