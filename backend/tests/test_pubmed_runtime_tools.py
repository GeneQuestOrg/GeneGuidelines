from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import patch

from backend.tools import pubmed_runtime as pubmed_mod


class _DummyMcp:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self):
        def decorator(fn):
            self.tools[getattr(fn, "__name__", "")] = fn
            return fn

        return decorator


class PubmedRuntimeToolsTests(unittest.TestCase):
    def _register(self) -> dict[str, Any]:
        dummy = _DummyMcp()
        pubmed_mod.register_pubmed_tools(dummy)
        return dummy.tools

    def test_pubmed_search_articles_deduplicates_pmids(self) -> None:
        tools = self._register()
        tool_fn = tools["pubmed_search_articles"]

        responses = [
            {"esearchresult": {"count": "2", "idlist": ["101", "202"]}},
            {"esearchresult": {"count": "2", "idlist": ["202", "303"]}},
        ]

        def _fake_get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            self.assertIn("esearch.fcgi", url)
            return responses.pop(0)

        with patch.object(pubmed_mod, "_http_get_json", side_effect=_fake_get_json):
            out = json.loads(
                tool_fn(
                    query="fibrous dysplasia",
                    query_variants_json=json.dumps(["fibrous dysplasia denosumab"]),
                    retmax=10,
                )
            )
        self.assertTrue(out.get("ok"))
        pmids = (out.get("result") or {}).get("pmids") or []
        self.assertEqual(pmids, ["101", "202", "303"])

    def test_pubmed_search_articles_paginates_until_empty(self) -> None:
        tools = self._register()
        tool_fn = tools["pubmed_search_articles"]
        responses = [
            {"esearchresult": {"count": "5", "idlist": ["1", "2"]}},
            {"esearchresult": {"count": "5", "idlist": ["3", "4"]}},
            {"esearchresult": {"count": "5", "idlist": ["5"]}},
        ]

        def _fake_get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            self.assertIn("esearch.fcgi", url)
            return responses.pop(0)

        with patch.object(pubmed_mod, "_http_get_json", side_effect=_fake_get_json):
            out = json.loads(tool_fn(query="x", query_variants_json="[]", retmax=2, max_analyze=10))
        self.assertTrue(out.get("ok"))
        result = out.get("result") or {}
        self.assertEqual(result.get("pmid_count"), 5)
        self.assertEqual(result.get("pmids"), ["1", "2", "3", "4", "5"])

    def test_pubmed_fetch_article_details_builds_evidence_cards(self) -> None:
        tools = self._register()
        tool_fn = tools["pubmed_fetch_article_details"]

        summary_payload = {
            "result": {
                "uids": ["1001"],
                "1001": {
                    "title": "Denosumab in fibrous dysplasia",
                    "authors": [{"name": "A. Doctor"}, {"name": "B. Specialist"}],
                    "source": "Clin Trial J",
                    "pubdate": "2024",
                    "articleids": [{"idtype": "doi", "value": "10.1000/xyz"}],
                },
            }
        }

        with patch.object(pubmed_mod, "_http_get_json", return_value=summary_payload):
            out = json.loads(tool_fn(pmids_json=json.dumps(["1001"]), include_abstracts=False))

        self.assertTrue(out.get("ok"))
        result = out.get("result") or {}
        self.assertEqual(result.get("article_count"), 1)
        article = (result.get("articles") or [])[0]
        self.assertEqual(article.get("doi"), "10.1000/xyz")
        cards = result.get("evidence_cards") or []
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].get("pmid"), "1001")
        self.assertEqual(result.get("total_requested"), 1)
        self.assertEqual(result.get("total_analyzed"), 1)

    def test_pubmed_fetch_article_details_batches_requests(self) -> None:
        tools = self._register()
        tool_fn = tools["pubmed_fetch_article_details"]

        payloads = [
            {"result": {"uids": ["1001"], "1001": {"title": "A", "authors": [], "source": "J", "pubdate": "2024"}}},
            {"result": {"uids": ["1002"], "1002": {"title": "B", "authors": [], "source": "J", "pubdate": "2023"}}},
        ]

        with (
            patch.dict("os.environ", {"PUBMED_TOOL_FETCH_BATCH_SIZE": "1"}),
            patch.object(pubmed_mod, "_http_get_json", side_effect=lambda *_args, **_kwargs: payloads.pop(0)),
        ):
            out = json.loads(tool_fn(pmids_json=json.dumps(["1001", "1002"]), include_abstracts=False))
        self.assertTrue(out.get("ok"))
        result = out.get("result") or {}
        self.assertEqual(result.get("article_count"), 2)
        self.assertEqual(result.get("total_requested"), 2)
        self.assertEqual(result.get("total_analyzed"), 2)

    def test_pubmed_browser_search_returns_error_when_disabled(self) -> None:
        tools = self._register()
        tool_fn = tools["pubmed_browser_search"]

        with patch.dict("os.environ", {"PUBMED_BROWSER_FALLBACK_ENABLED": "0"}):
            out = json.loads(tool_fn(query="fibrous dysplasia", max_results=5))
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("message"), "browser_fallback_disabled")


if __name__ == "__main__":
    unittest.main()
