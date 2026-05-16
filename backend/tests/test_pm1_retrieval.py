from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

import httpx

from backend.flows.pubmed import retrieval as retrieval_mod
from backend.tools import pubmed_runtime as pubmed_mod


class _FakeEsearch:
    """Returns distinct PMIDs per call so we can verify 5 searches + dedup."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        # One page of results per variant; second page empty to end pagination.
        self._per_call = [
            ["1001", "1002"],
            ["1003"],
            ["1004", "1001"],
            ["1005"],
            ["1006"],
        ]

    def __call__(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append(dict(params or {}))
        if "esearch.fcgi" not in url:
            raise AssertionError(f"unexpected url {url}")
        idx = (len(self.calls) - 1) % len(self._per_call)
        idlist = self._per_call[idx]
        return {"esearchresult": {"count": str(len(idlist)), "idlist": idlist}}


def _fake_esummary(pmids: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"uids": list(pmids)}
    for p in pmids:
        result[p] = {
            "title": f"Article {p}",
            "authors": [{"name": "Smith J"}],
            "source": "J Clin Med",
            "pubdate": "2024",
            "articleids": [{"idtype": "doi", "value": f"10.0/{p}"}],
        }
    return {"result": result}


class RunPm1RetrievalTests(unittest.TestCase):
    def test_runs_five_searches_and_returns_unique_articles(self) -> None:
        fake = _FakeEsearch()
        initial_context = {"initial": {"title": "fibrous dysplasia"}}

        def _get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            if "esearch.fcgi" in url:
                return fake(url, params)
            if "esummary.fcgi" in url:
                ids = (params or {}).get("id", "")
                pmids = [p for p in str(ids).split(",") if p]
                return _fake_esummary(pmids)
            raise AssertionError(f"unexpected url {url}")

        with (
            patch.object(pubmed_mod, "_http_get_json", side_effect=_get_json),
            patch.object(pubmed_mod, "_http_get_text", return_value=""),
        ):
            out = retrieval_mod.run_pm1_retrieval(initial_context, retmax=50, max_analyze=50)

        self.assertEqual(out["query_text"], "fibrous dysplasia")
        self.assertGreaterEqual(len(out["query_variants"]), 5)
        self.assertFalse(out["fallback_used"])
        self.assertGreaterEqual(len(fake.calls), 5)
        expected_pmids = {"1001", "1002", "1003", "1004", "1005", "1006"}
        returned_pmids = {a["pmid"] for a in out["articles"]}
        self.assertEqual(returned_pmids, expected_pmids)
        self.assertEqual(len(out["evidence_cards"]), len(out["articles"]))
        self.assertEqual(out["total_requested"], len(expected_pmids))
        self.assertEqual(out["total_analyzed"], len(expected_pmids))
        self.assertEqual(out["retrieval_channel"], "primary_get")
        self.assertEqual(out["fallback_reason"], "none")
        self.assertGreater(out["request_count"], 0)
        self.assertIn("evidence_manifest", out)
        high_tier_call = fake.calls[0]
        self.assertIn("Meta-Analysis", str(high_tier_call.get("term", "")))

    def test_missing_title_returns_fallback_payload(self) -> None:
        with (
            patch.object(pubmed_mod, "_http_get_json") as j_mock,
            patch.object(pubmed_mod, "_http_get_text") as t_mock,
        ):
            out = retrieval_mod.run_pm1_retrieval({"initial": {}})
        j_mock.assert_not_called()
        t_mock.assert_not_called()
        self.assertTrue(out["fallback_used"])
        self.assertEqual(out["articles"], [])
        self.assertEqual(out["retrieval_error"], "missing_ticket_title")

    def test_empty_esearch_reports_no_articles_but_keeps_variants(self) -> None:
        def _get_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            if "esearch.fcgi" in url:
                return {"esearchresult": {"count": "0", "idlist": []}}
            raise AssertionError("esummary should not be called when no PMIDs")

        with (
            patch.object(pubmed_mod, "_http_get_json", side_effect=_get_json),
            patch.object(pubmed_mod, "_http_get_text", return_value=""),
        ):
            out = retrieval_mod.run_pm1_retrieval({"initial": {"title": "orphan disease"}})

        self.assertEqual(out["articles"], [])
        self.assertGreaterEqual(len(out["query_variants"]), 5)
        self.assertTrue(out["fallback_used"])

    def test_uses_browser_fallback_only_for_transport_errors(self) -> None:
        initial_context = {"initial": {"title": "fibrous dysplasia"}}
        request = httpx.Request("GET", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi")
        response = httpx.Response(429, request=request)

        with (
            patch.object(pubmed_mod, "_http_get_json", side_effect=httpx.HTTPStatusError("rate limited", request=request, response=response)),
            patch.object(pubmed_mod, "_http_get_text", return_value=""),
            patch.object(retrieval_mod, "pubmed_browser_search_impl", return_value={"pmids": ["9001", "9002"], "request_count": 1}),
            patch.object(retrieval_mod, "fetch_article_details_impl", return_value={"articles": [], "evidence_cards": [], "total_requested": 2, "total_analyzed": 0, "total_with_abstract": 0}),
        ):
            out = retrieval_mod.run_pm1_retrieval(initial_context, retmax=50, max_analyze=50)

        self.assertTrue(out["fallback_used"])
        self.assertEqual(out["retrieval_channel"], "fallback_browser")
        self.assertEqual(out["fallback_reason"], "transport_error")

    def test_does_not_use_browser_fallback_for_non_transport_errors(self) -> None:
        initial_context = {"initial": {"title": "fibrous dysplasia"}}

        def _raise_non_transport(_url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            raise ValueError("unexpected parser issue")

        with (
            patch.object(pubmed_mod, "_http_get_json", side_effect=_raise_non_transport),
            patch.object(pubmed_mod, "_http_get_text", return_value=""),
            patch.object(retrieval_mod, "pubmed_browser_search_impl") as fallback_mock,
        ):
            out = retrieval_mod.run_pm1_retrieval(initial_context, retmax=50, max_analyze=50)

        fallback_mock.assert_not_called()
        self.assertEqual(out["retrieval_channel"], "none")
        self.assertTrue(out["fallback_used"])

    def test_runs_global_backfill_when_corpus_too_small(self) -> None:
        initial_context = {"initial": {"title": "fibrous dysplasia"}}
        called_queries: list[str] = []

        def _search_impl(
            query: str,
            *,
            query_variants: list[str] | None = None,
            retmax: int | None = None,
            max_analyze: int | None = None,
            mindate: str = "",
            maxdate: str = "",
            article_types: list[str] | None = None,
        ) -> dict[str, Any]:
            called_queries.append(query)
            if len(called_queries) <= 5:
                pmids = [f"20{len(called_queries)}"]
            else:
                start = 3000 + (len(called_queries) - 6) * 60
                pmids = [str(start + i) for i in range(60)]
            return {
                "pmids": pmids,
                "request_count": 1,
                "http_status_stats": {"http_429": 0, "http_5xx": 0, "http_4xx": 0, "timeout": 0, "network": 0},
                "transport_error_classes": [],
                "raw_runs": [{"total_found": len(pmids)}],
            }

        with (
            patch.object(retrieval_mod, "search_articles_impl", side_effect=_search_impl),
            patch.object(
                retrieval_mod,
                "fetch_article_details_impl",
                return_value={
                    "articles": [{"pmid": str(1000 + i), "title": f"T{i}"} for i in range(125)],
                    "evidence_cards": [{"pmid": str(1000 + i)} for i in range(125)],
                    "total_requested": 125,
                    "total_analyzed": 125,
                    "total_with_abstract": 0,
                    "request_count": 1,
                    "http_status_stats": {"http_429": 0, "http_5xx": 0, "http_4xx": 0, "timeout": 0, "network": 0},
                    "retrieval_channel": "primary_get",
                },
            ),
        ):
            out = retrieval_mod.run_pm1_retrieval(initial_context, retmax=50, max_analyze=50)

        self.assertGreater(len(called_queries), 5)
        self.assertGreaterEqual(len(out["query_variants"]), 6)
        self.assertEqual(out["total_analyzed"], 125)


class QueryNormalizationTests(unittest.TestCase):
    def test_normalize_query_term_strips_supported_suffixes(self) -> None:
        cases = (
            ("Fibrous dysplasia clinical guideline", "Fibrous dysplasia"),
            ("Marfan syndrome guidelines", "Marfan syndrome"),
            ("Paget disease management guideline", "Paget disease"),
            ("Achondroplasia evidence-based guideline", "Achondroplasia"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(retrieval_mod._normalize_query_term(raw), expected)

    def test_normalize_query_term_leaves_unsupported_suffix_cases_unchanged(self) -> None:
        cases = (
            ("Fibrous dysplasia", "Fibrous dysplasia"),
            ("", ""),
            ("guideline", "guideline"),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(retrieval_mod._normalize_query_term(raw), expected)

    def test_search_receives_normalized_term(self) -> None:
        recorded_queries: list[str] = []

        def _stub_search(
            query: str,
            *,
            query_variants: list[str] | None = None,
            retmax: int | None = None,
            max_analyze: int | None = None,
            mindate: str = "",
            maxdate: str = "",
            article_types: list[str] | None = None,
        ) -> dict[str, Any]:
            recorded_queries.append(query)
            return {
                "pmids": [],
                "request_count": 0,
                "http_status_stats": {"http_429": 0, "http_5xx": 0, "http_4xx": 0, "timeout": 0, "network": 0},
                "transport_error_classes": [],
                "raw_runs": [],
            }

        with patch.object(retrieval_mod, "search_articles_impl", side_effect=_stub_search):
            out = retrieval_mod.run_pm1_retrieval(
                {"initial": {"title": "Fibrous dysplasia clinical guideline"}},
                retmax=10,
                max_analyze=10,
            )

        for q in recorded_queries:
            self.assertNotIn("clinical guideline", q, msg=f"query still contains suffix: {q!r}")
        self.assertEqual(out["query_text"], "Fibrous dysplasia clinical guideline")
        self.assertEqual(out["normalized_query_text"], "Fibrous dysplasia")

class GeneticsFilterAndConfigTests(unittest.TestCase):
    """Tests for genetics filter in domain queries and updated config defaults."""

    def test_non_high_tier_domain_queries_contain_genetics_filter(self) -> None:
        for domain, query_template, _article_types in retrieval_mod._DOMAIN_QUERIES:
            if domain == "high_tier":
                continue
            self.assertIn(
                "gene OR genetic OR mutation",
                query_template,
                msg=f"Domain {domain!r} query missing genetics filter: {query_template!r}",
            )

    def test_high_tier_domain_query_unchanged(self) -> None:
        high_tier = next(
            (q for name, q, _ in retrieval_mod._DOMAIN_QUERIES if name == "high_tier"),
            None,
        )
        self.assertIsNotNone(high_tier)
        # high_tier should remain a simple title placeholder without extra filters
        self.assertNotIn("gene OR genetic", high_tier)

    def test_config_defaults_are_updated(self) -> None:
        from backend.config import (
            PUBMED_RETRIEVAL_MIN_PMIDS_PER_DOMAIN,
            PUBMED_RETRIEVAL_TARGET_PMIDS,
        )
        self.assertEqual(PUBMED_RETRIEVAL_MIN_PMIDS_PER_DOMAIN, 50)
        self.assertEqual(PUBMED_RETRIEVAL_TARGET_PMIDS, 800)

class RelevanceOrderingTests(unittest.TestCase):
    """Tests for stable relevance-based sorting of retrieved articles."""

    def _make_articles(self, titles: list[str]) -> list[dict]:
        return [{"pmid": str(i + 1), "title": title} for i, title in enumerate(titles)]

    def _make_evidence_cards(self, articles: list[dict]) -> list[dict]:
        return [{"pmid": a["pmid"]} for a in articles]

    def test_articles_are_relevance_ordered_by_title_match(self) -> None:
        """Article with more disease-term matches in title comes first."""
        articles_in = self._make_articles([
            "Unrelated study",                         # 0 matches for "fibrous dysplasia"
            "Fibrous dysplasia diagnosis",             # 2 matches
            "Fibrous dysplasia treatment outcomes",    # 2 matches (tie)
        ])
        evidence_cards_in = self._make_evidence_cards(articles_in)

        def _stub_search(query, *, query_variants=None, retmax=None, max_analyze=None,
                         mindate="", maxdate="", article_types=None):
            return {
                "pmids": [a["pmid"] for a in articles_in],
                "request_count": 1,
                "http_status_stats": {"http_429": 0, "http_5xx": 0, "http_4xx": 0, "timeout": 0, "network": 0},
                "transport_error_classes": [],
                "raw_runs": [{"total_found": len(articles_in)}],
            }

        with (
            patch.object(retrieval_mod, "search_articles_impl", side_effect=_stub_search),
            patch.object(
                retrieval_mod,
                "fetch_article_details_impl",
                return_value={
                    "articles": articles_in,
                    "evidence_cards": evidence_cards_in,
                    "total_requested": len(articles_in),
                    "total_analyzed": len(articles_in),
                    "total_with_abstract": 0,
                    "request_count": 1,
                    "http_status_stats": {"http_429": 0, "http_5xx": 0, "http_4xx": 0, "timeout": 0, "network": 0},
                    "retrieval_channel": "primary_get",
                },
            ),
        ):
            out = retrieval_mod.run_pm1_retrieval(
                {"initial": {"title": "fibrous dysplasia"}},
                retmax=50,
                max_analyze=50,
            )

        articles_out = out["articles"]
        # Total count preserved
        self.assertEqual(len(articles_out), len(articles_in))
        # "Unrelated study" should be last (0 matches)
        unrelated_idx = next(
            i for i, a in enumerate(articles_out) if "Unrelated" in a["title"]
        )
        self.assertEqual(unrelated_idx, len(articles_out) - 1)

    def test_relevance_ordering_length_preserved(self) -> None:
        """Sorting must not drop or duplicate articles."""
        articles_in = self._make_articles([
            "Article A disease",
            "Article B unrelated",
            "Article C disease variant",
        ])
        evidence_cards_in = self._make_evidence_cards(articles_in)

        def _stub_search(query, *, query_variants=None, retmax=None, max_analyze=None,
                         mindate="", maxdate="", article_types=None):
            return {
                "pmids": [a["pmid"] for a in articles_in],
                "request_count": 1,
                "http_status_stats": {"http_429": 0, "http_5xx": 0, "http_4xx": 0, "timeout": 0, "network": 0},
                "transport_error_classes": [],
                "raw_runs": [{"total_found": len(articles_in)}],
            }

        with (
            patch.object(retrieval_mod, "search_articles_impl", side_effect=_stub_search),
            patch.object(
                retrieval_mod,
                "fetch_article_details_impl",
                return_value={
                    "articles": articles_in,
                    "evidence_cards": evidence_cards_in,
                    "total_requested": len(articles_in),
                    "total_analyzed": len(articles_in),
                    "total_with_abstract": 0,
                    "request_count": 1,
                    "http_status_stats": {"http_429": 0, "http_5xx": 0, "http_4xx": 0, "timeout": 0, "network": 0},
                    "retrieval_channel": "primary_get",
                },
            ),
        ):
            out = retrieval_mod.run_pm1_retrieval(
                {"initial": {"title": "disease"}},
                retmax=50,
                max_analyze=50,
            )

        articles_out = out["articles"]
        self.assertEqual(len(articles_out), len(articles_in))
        out_pmids = [a["pmid"] for a in articles_out]
        in_pmids = [a["pmid"] for a in articles_in]
        self.assertEqual(sorted(out_pmids), sorted(in_pmids))


if __name__ == "__main__":
    unittest.main()
