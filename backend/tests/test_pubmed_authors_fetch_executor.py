from __future__ import annotations

import asyncio

from backend.executors.base import FlowRuntimeBundle, NodeInput
from backend.executors.pubmed_authors_fetch_executor import PubmedAuthorsFetchExecutor


def test_pubmed_fetch_paginates_full_set_with_max_results_as_page_size(monkeypatch) -> None:
    """``max_results`` is the per-esearch PAGE size (retmax); the TOTAL budget is
    ``DOCTOR_FINDER_MAX_PMIDS`` (config), which the runtime paginates up to. A doctor
    run must capture the whole relevant author set, not a single ``max_results`` slice —
    so 100 available PMIDs (below the budget) are all scanned even with page_size=50."""
    from backend.config import DOCTOR_FINDER_MAX_PMIDS

    captured: dict[str, object] = {}

    def _fake_search(query: str, *, retmax: int | None = None, max_analyze: int | None = None, **_kwargs):
        captured["query"] = query
        captured["retmax"] = retmax
        captured["max_analyze"] = max_analyze
        return {"pmids": [str(i) for i in range(1, 101)], "pmid_count": 100}

    def _fake_fetch(pmids: list[str]):
        captured["pmids"] = list(pmids)
        return {
            "articles": [
                {
                    "pmid": p,
                    "title": f"Fibrous dysplasia cohort PMID {p}",
                    "abstract": "Patients with polyostotic fibrous dysplasia.",
                    "authors": [],
                }
                for p in pmids
            ]
        }

    monkeypatch.setattr(
        "backend.tools.pubmed_runtime.search_articles_impl",
        _fake_search,
    )
    monkeypatch.setattr(
        "backend.tools.pubmed_runtime.fetch_authors_with_affiliations_impl",
        _fake_fetch,
    )

    executor = PubmedAuthorsFetchExecutor()

    async def _run() -> None:
        out = await executor.execute(
            NodeInput(
                node_config={"node_id": "df-1"},
                context={},
                initial_data={
                    "disease_name": "fibrous dysplasia",
                    "disease_aliases": ["FD"],
                    "max_results": 50,
                    "clinical_focus": True,
                },
                flow_runtime=FlowRuntimeBundle(store={}, event_queue=None, emit_fn=lambda _q, _p: None),
            )
        )
        assert out.data["ok"] is True
        # Full available set scanned (100), not capped to the page size (50).
        assert out.data["total_papers_scanned"] == 100

    asyncio.run(_run())

    # max_results -> per-page retmax; total budget -> DOCTOR_FINDER_MAX_PMIDS.
    assert captured["retmax"] == 50
    assert captured["max_analyze"] == DOCTOR_FINDER_MAX_PMIDS
    assert len(captured["pmids"]) == 100
    q = str(captured["query"])
    assert "humans[MeSH Terms]" in q
    assert "[Title/Abstract]" in q
    assert '"fibrous dysplasia"' in q.lower()
    assert "veterinary" in q
    assert " OR dog " not in q


def test_pubmed_fetch_can_disable_clinical_focus(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_search(query: str, *, retmax: int | None = None, max_analyze: int | None = None, **_kwargs):
        captured["query"] = query
        return {"pmids": ["1"], "pmid_count": 1}

    def _fake_fetch(pmids: list[str]):
        return {
            "articles": [
                {
                    "pmid": p,
                    "title": f"Fibrous dysplasia review {p}",
                    "abstract": "",
                    "authors": [],
                }
                for p in pmids
            ]
        }

    monkeypatch.setattr(
        "backend.tools.pubmed_runtime.search_articles_impl",
        _fake_search,
    )
    monkeypatch.setattr(
        "backend.tools.pubmed_runtime.fetch_authors_with_affiliations_impl",
        _fake_fetch,
    )

    executor = PubmedAuthorsFetchExecutor()

    async def _run() -> None:
        out = await executor.execute(
            NodeInput(
                node_config={"node_id": "df-1"},
                context={},
                initial_data={
                    "disease_name": "fibrous dysplasia",
                    "disease_aliases": ["FD"],
                    "max_results": 10,
                    "clinical_focus": False,
                },
                flow_runtime=FlowRuntimeBundle(store={}, event_queue=None, emit_fn=lambda _q, _p: None),
            )
        )
        assert out.data["ok"] is True

    asyncio.run(_run())
    assert "humans[MeSH Terms]" not in str(captured["query"])
