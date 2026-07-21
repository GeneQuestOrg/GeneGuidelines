"""Tests for the shelf-builder (step 1 of the research pipeline).

In-memory SQLite (StaticPool so the thread-pool sees the same DB) + the GL-4 test
pattern. No network: the PubMed/Bookshelf retrieval is monkeypatched. Covers the
repo replace, the GuidelineShelf preset validators, the search + write executors,
and the flow-spec / registry wiring. The live FD recall check lives OUTSIDE the
workflow in scripts/validate_shelf_fd.py.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import backend.guidelines.orm  # noqa: F401 — registers tables on the shared metadata
from backend.agents.schemas import PRESET_OUTPUT_SCHEMAS, GuidelineShelfDoc, GuidelineShelfOutput
from backend.executors import EXECUTOR_REGISTRY
from backend.executors.base import NodeInput
from backend.executors.guideline_shelf_search_executor import GuidelineShelfSearchExecutor
from backend.executors.guideline_shelf_write_executor import GuidelineShelfWriteExecutor
from backend.guidelines.repository import SqlaGuidelinesRepo
from backend.shared.persistence.schema import metadata


@pytest.fixture
def repo() -> SqlaGuidelinesRepo:
    engine = create_engine(
        "sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    return SqlaGuidelinesRepo(engine=engine)


# ── repo replace_source_documents ──────────────────────────────────────────


def test_replace_source_documents_round_trip(repo: SqlaGuidelinesRepo) -> None:
    def doc(doc_id: str, pmid: str | None = None, bookshelf: str | None = None) -> dict:
        return {
            "id": doc_id, "role": "Base consensus", "title": f"Doc {doc_id}",
            "authors": "A, B", "journal": "J", "year": 2024, "scope": "s",
            "covers": ["Dx"], "pmid": pmid, "bookshelf": bookshelf,
        }

    repo.replace_source_documents("fd", [doc("a", pmid="1"), doc("b", pmid="2")])
    assert [d.doc_id for d in repo.list_source_documents("fd")] == ["a", "b"]
    # Re-run with a different set replaces wholesale (no dup, no leftover "b").
    repo.replace_source_documents("fd", [doc("c", bookshelf="NBK1")])
    docs = repo.list_source_documents("fd")
    assert [d.doc_id for d in docs] == ["c"]
    assert docs[0].bookshelf == "NBK1"


# ── GuidelineShelf preset validators ───────────────────────────────────────


def test_shelf_preset_registered() -> None:
    assert PRESET_OUTPUT_SCHEMAS.get("guideline_shelf") is GuidelineShelfOutput


def test_shelf_doc_accepts_pmid_and_bookshelf() -> None:
    a = GuidelineShelfDoc(pmid="31196103", title="Consensus statement", kind="base_consensus")
    assert a.pmid == "31196103" and a.kind == "base_consensus"
    b = GuidelineShelfDoc(bookshelf="NBK274564", title="GeneReviews chapter", kind="reference_compendium")
    assert b.bookshelf == "NBK274564"


def test_shelf_doc_rejects_no_identifier() -> None:
    with pytest.raises(ValidationError):
        GuidelineShelfDoc(title="No id anywhere", kind="other")


def test_shelf_doc_rejects_bad_kind_and_nonpmid() -> None:
    with pytest.raises(ValidationError):
        GuidelineShelfDoc(pmid="31196103", title="t", kind="not-a-kind")
    with pytest.raises(ValidationError):
        GuidelineShelfDoc(pmid="PMID123", title="t", kind="other")


# ── search executor (monkeypatched retrieval) ──────────────────────────────


def test_shelf_search_returns_candidates(monkeypatch) -> None:
    fake = [
        {"pmid": "31196103", "title": "Best practice management guidelines", "authors": "Javaid", "journal": "OJRD", "year": "2019", "abstract": "a"},
        {"bookshelf": "NBK274564", "title": "Fibrous Dysplasia / MAS", "authors": "Boyce", "journal": "GeneReviews", "year": "continuously updated", "abstract": ""},
    ]
    monkeypatch.setattr(
        "backend.executors.guideline_shelf_search_executor._collect_shelf_candidates",
        lambda name, gene=None: fake,
    )
    ex = GuidelineShelfSearchExecutor()
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context={}, initial_data={"disease_name": "Fibrous Dysplasia"}))
    )
    assert out.data["ok"] is True
    assert out.data["candidate_count"] == 2


# ── gene-aware shelf search (ultra-rare: name finds ~0 sources, gene finds them) ──


def test_collect_shelf_candidates_ors_gene_into_pubmed_and_books(monkeypatch) -> None:
    """Gene is OR'd into every PubMed query (Title/Abstract) and adds Bookshelf queries."""
    from backend.executors import guideline_shelf_search_executor as se

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(se, "_esearch_ids", lambda db, term, retmax: calls.append((db, term)) or [])
    # No pmids returned → fetch_article_details_impl is never reached (no network).
    se._collect_shelf_candidates("Ultra Rare Disease", gene="PUS3")

    pubmed_terms = [t for db, t in calls if db == "pubmed"]
    books_terms = [t for db, t in calls if db == "books"]
    assert pubmed_terms and books_terms
    for t in pubmed_terms:
        assert '"PUS3"[Title/Abstract]' in t  # gene OR'd in, Title/Abstract scoped
        assert '"Ultra Rare Disease"[Title/Abstract]' in t  # disease name kept
        assert " OR " in t  # OR (broaden) not AND (narrow)
        assert "[Gene]" not in t  # no invalid PubMed field
    # GeneReviews is gene-titled → a gene Bookshelf query is added.
    assert any('"PUS3"' in t for t in books_terms)


def test_collect_shelf_candidates_omits_gene_when_absent_or_short(monkeypatch) -> None:
    from backend.executors import guideline_shelf_search_executor as se

    for gene in (None, "", "X"):  # absent / empty / too-short (<3 chars)
        calls: list[tuple[str, str]] = []
        monkeypatch.setattr(se, "_esearch_ids", lambda db, term, retmax: calls.append((db, term)) or [])
        se._collect_shelf_candidates("Fibrous Dysplasia", gene=gene)
        pubmed_terms = [t for db, t in calls if db == "pubmed"]
        assert pubmed_terms
        for t in pubmed_terms:
            assert "OR" not in t.split("AND")[0]  # disease block is name-only (no gene OR)
            assert '"Fibrous Dysplasia"[Title/Abstract]' in t


def test_shelf_search_resolves_gene_from_disease_row(monkeypatch) -> None:
    """Executor resolves the causative gene from the disease_slug row and threads it in."""
    from backend.executors import guideline_shelf_search_executor as se

    captured: dict[str, object] = {}

    def _fake_collect(name, gene=None):
        captured["name"] = name
        captured["gene"] = gene
        return [{"pmid": "1", "title": "t", "authors": "", "journal": "", "year": "2020", "abstract": ""}]

    monkeypatch.setattr(se, "_collect_shelf_candidates", _fake_collect)
    monkeypatch.setattr("backend.content_db.get_disease_gene", lambda slug: "PUS3")
    ex = se.GuidelineShelfSearchExecutor()
    out = asyncio.run(
        ex.execute(
            NodeInput(
                node_config={},
                context={},
                initial_data={"disease_name": "Ultra Rare", "disease_slug": "pus3-syndrome"},
            )
        )
    )
    assert out.data["ok"] is True
    assert captured["gene"] == "PUS3"


def test_shelf_search_explicit_gene_wins_over_row(monkeypatch) -> None:
    from backend.executors import guideline_shelf_search_executor as se

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        se, "_collect_shelf_candidates", lambda name, gene=None: captured.update(gene=gene) or [{"pmid": "1", "title": "t"}]
    )
    # Row resolver must NOT be consulted when an explicit gene is supplied.
    monkeypatch.setattr(
        "backend.content_db.get_disease_gene",
        lambda slug: (_ for _ in ()).throw(AssertionError("row resolver should not be called")),
    )
    ex = se.GuidelineShelfSearchExecutor()
    out = asyncio.run(
        ex.execute(
            NodeInput(
                node_config={},
                context={},
                initial_data={"disease_name": "D", "disease_slug": "s", "gene": "ACVR1"},
            )
        )
    )
    assert out.data["ok"] is True
    assert captured["gene"] == "ACVR1"


def test_shelf_search_missing_disease_name() -> None:
    ex = GuidelineShelfSearchExecutor()
    out = asyncio.run(ex.execute(NodeInput(node_config={}, context={}, initial_data={})))
    assert out.data["ok"] is False
    assert "disease_name" in out.data["error"].lower()


# ── write executor (classified docs → guideline_source_documents) ──────────


def test_shelf_write_maps_and_replaces(repo: SqlaGuidelinesRepo) -> None:
    classified = {
        "docs": [
            {"pmid": "31196103", "title": "Consensus", "kind": "base_consensus", "role": "Base consensus", "covers": ["Dx"]},
            {"pmid": "38010041", "title": "Children update", "kind": "update", "updates_note": "denosumab schedule"},
            {"bookshelf": "NBK274564", "title": "GeneReviews", "kind": "reference_compendium"},
            {"pmid": "31196103", "title": "dup", "kind": "base_consensus"},  # duplicate id → dropped
        ]
    }
    context = {"gsb-classify": classified}
    initial = {"disease_slug": "fd", "disease_name": "Fibrous Dysplasia"}
    ex = GuidelineShelfWriteExecutor(repo=repo)
    out = asyncio.run(ex.execute(NodeInput(node_config={}, context=context, initial_data=initial)))
    assert out.data["ok"] is True
    assert out.data["docCount"] == 3  # dup dropped

    docs = {d.doc_id: d for d in repo.list_source_documents("fd")}
    assert set(docs) == {"31196103", "38010041", "NBK274564"}
    assert docs["38010041"].is_new is True  # kind=update → isNew
    assert docs["38010041"].updates_note == "denosumab schedule"
    assert docs["NBK274564"].bookshelf == "NBK274564"
    assert docs["NBK274564"].role == "Reference compendium"  # default role from kind


def test_shelf_write_normalizes_junk_journal_and_year(repo: SqlaGuidelinesRepo) -> None:
    # The model occasionally emits junk (journal="gene", a timestamp year). The
    # writer must not persist that — blank the journal, salvage the year.
    classified = {
        "docs": [
            {
                "bookshelf": "NBK274564", "title": "GeneReviews",
                "kind": "reference_compendium", "journal": "gene", "year": "2015/02/26 00:00",
            },
            {"pmid": "31196103", "title": "Consensus", "kind": "base_consensus", "journal": "Orphanet J Rare Dis", "year": "2019"},
        ]
    }
    initial = {"disease_slug": "fd", "disease_name": "Fibrous Dysplasia"}
    ex = GuidelineShelfWriteExecutor(repo=repo)
    out = asyncio.run(ex.execute(NodeInput(node_config={}, context={"gsb-classify": classified}, initial_data=initial)))
    assert out.data["ok"] is True
    docs = {d.doc_id: d for d in repo.list_source_documents("fd")}
    assert docs["NBK274564"].journal == ""  # junk one-word lowercase token dropped
    assert docs["NBK274564"].year == "2015"  # year salvaged out of the timestamp
    assert docs["31196103"].journal == "Orphanet J Rare Dis"  # real journal untouched
    assert docs["31196103"].year == "2019"


def test_shelf_write_no_docs_is_error(repo: SqlaGuidelinesRepo) -> None:
    ex = GuidelineShelfWriteExecutor(repo=repo)
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context={"gsb-classify": {"docs": []}}, initial_data={"disease_slug": "fd"}))
    )
    assert out.data["ok"] is False


# ── flow spec + registry wiring ────────────────────────────────────────────


def test_shelf_executors_registered() -> None:
    from backend.executors import EXECUTOR_REGISTRY
    from backend.executors.guideline_bibliography_write_executor import GuidelineBibliographyWriteExecutor

    assert EXECUTOR_REGISTRY["guideline_shelf_search"] is GuidelineShelfSearchExecutor
    assert EXECUTOR_REGISTRY["guideline_shelf_write"] is GuidelineShelfWriteExecutor
    assert EXECUTOR_REGISTRY["guideline_bibliography_write"] is GuidelineBibliographyWriteExecutor


def test_shelf_flow_spec_valid_and_connected() -> None:
    spec_path = (
        Path(__file__).resolve().parent.parent / "flows" / "specs" / "guideline_shelf_build.json"
    )
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["flow_key"] == "guideline_shelf_build"
    nodes = {n["node_id"]: n for n in spec["nodes"]}
    assert nodes["gsb-search"]["node_type"] == "guideline_shelf_search"
    assert nodes["gsb-write"]["node_type"] == "guideline_shelf_write"
    assert nodes["gsb-bib"]["node_type"] == "guideline_bibliography_write"
    assert nodes["gsb-classify"]["prompt_mode"] == "simple"
    assert nodes["gsb-classify"]["output_schema_key"] == "guideline_shelf"
    assert "considered" in nodes["gsb-classify"]["prompt"]
    pairs = {(e["source_node_id"], e["target_node_id"]) for e in spec["edges"]}
    assert pairs == {
        ("start", "gsb-search"),
        ("gsb-search", "gsb-classify"),
        ("gsb-classify", "gsb-write"),
        ("gsb-write", "gsb-bib"),
        ("gsb-bib", "end"),
    }


def test_enrich_docs_from_pubmed_backfills_blank_author_year(monkeypatch) -> None:
    """The write step must backfill blank authors/year/journal from PubMed by
    PMID — the classify node drops that metadata, which rendered "· n/a"."""
    from backend.executors import guideline_shelf_write_executor as wex

    docs = [
        {"pmid": "33653979", "authors": "", "year": "n/a", "journal": "", "title": "A"},
        {"pmid": "999", "authors": "Existing A", "year": "2010", "journal": "J", "title": "B"},
        {"pmid": None, "bookshelf": "NBK1", "authors": "", "year": "n/a", "journal": ""},
    ]

    def _fake_meta(pmids):
        assert pmids == ["33653979", "999"]  # only real PMIDs, order preserved
        return [
            {"pmid": "33653979", "authors": "Ricca AM, Han IC", "journal": "Curr Opin Ophthalmol", "year": 2021},
            {"pmid": "999", "authors": "Other Z", "journal": "Other J", "year": 2020},
        ]

    monkeypatch.setattr(
        "backend.services.official_guidelines_finder._pubmed_metadata", _fake_meta
    )
    wex._enrich_docs_from_pubmed(docs)

    # blank doc is filled from PubMed
    assert docs[0]["authors"] == "Ricca AM, Han IC"
    assert docs[0]["year"] == "2021"
    assert docs[0]["journal"] == "Curr Opin Ophthalmol"
    # a doc that already had metadata is NOT clobbered
    assert docs[1]["authors"] == "Existing A"
    assert docs[1]["year"] == "2010"
    # a doc without a PMID is left untouched
    assert docs[2]["year"] == "n/a"
    assert docs[2]["authors"] == ""


def test_enrich_docs_from_pubmed_soft_fails(monkeypatch) -> None:
    """A PubMed error must not raise — docs keep their existing (blank) values."""
    from backend.executors import guideline_shelf_write_executor as wex

    def _boom(_pmids):
        raise RuntimeError("network down")

    monkeypatch.setattr(
        "backend.services.official_guidelines_finder._pubmed_metadata", _boom
    )
    docs = [{"pmid": "1", "authors": "", "year": "n/a", "journal": ""}]
    wex._enrich_docs_from_pubmed(docs)  # must not raise
    assert docs[0]["year"] == "n/a"
