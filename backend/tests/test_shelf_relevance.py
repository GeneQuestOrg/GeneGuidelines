"""Shelf relevance: a document about another disease never stays on a shelf (backend/guidelines/relevance.py, the shelf builder, alembic a7d2c9e4f1b3). No network: the GeneReviews index is built from inline text."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.guidelines.relevance import (
    MATCH,
    MISMATCH,
    UNKNOWN,
    assess,
    count_mentions,
    identity_from_disease,
    parse_genes,
)
from backend.tools.genereviews_index import parse_index

REPO_ROOT = Path(__file__).resolve().parents[2]

TITLES = "#GR_shortname\tGR_Title\tNBK_id\tPMID\nmccune-albright\tFibrous Dysplasia / McCune-Albright Syndrome\tNBK274564\t25719192\nschinzel-giedion\tSchinzel-Giedion Syndrome\tNBK601394\t38452171\nptdss1-lmhd\tPTDSS1-Related Lenz-Majewski Hyperostotic Dysplasia\tNBK621299\t41818602\n"
GENES = "mccune-albright|NBK274564|GNAS|Fibrous Dysplasia / McCune-Albright Syndrome\nschinzel-giedion|NBK601394|SETBP1|Schinzel-Giedion Syndrome\nptdss1-lmhd|NBK621299|PTDSS1|PTDSS1-Related Lenz-Majewski Hyperostotic Dysplasia\n"
OMIM = "#NBK_id\tGR_shortname\tOMIM\nNBK274564\tmccune-albright\t174800\nNBK601394\tschinzel-giedion\t269150\nNBK621299\tptdss1-lmhd\t151050\n"
INDEX = parse_index(TITLES, GENES, OMIM)

PUS3 = identity_from_disease({"slug": "severe-growth-deficiency-strabismus-extensive-dermal-melanocytos", "name": "Severe growth deficiency-strabismus-extensive dermal melanocytosis-intellectual disability syndrome", "nameShort": "Severe growth deficiency", "omim": "617051", "gene": "PUS3"})
FD = identity_from_disease({"slug": "fd", "name": "Fibrous Dysplasia", "nameShort": "FD", "omim": "174800", "gene": "GNAS"})
MAS = identity_from_disease({"slug": "mas", "name": "McCune-Albright Syndrome", "nameShort": "MAS", "omim": "174800", "gene": "GNAS"})
NOONAN = identity_from_disease({"slug": "noonan", "name": "Noonan Syndrome", "nameShort": "Noonan", "omim": "163950", "gene": "PTPN11, SOS1, RAF1, KRAS, RIT1 (RAS-MAPK)"})


def test_genereviews_index_parses_titles_genes_and_omim():
    chapter = INDEX["NBK601394"]
    assert chapter.title == "Schinzel-Giedion Syndrome" and chapter.genes == ("SETBP1",) and chapter.omim == ("269150",)


def test_identity_parses_genes_and_eponyms():
    assert parse_genes("PTPN11, SOS1, RAF1, KRAS, RIT1 (RAS-MAPK)") == ("PTPN11", "SOS1", "RAF1", "KRAS", "RIT1")
    assert "noonan" in NOONAN.phrases() and "mccune albright" in MAS.phrases()
    assert FD.phrases() == ("fibrous dysplasia",) and FD.tokens() == ("FD", "GNAS")


def test_the_two_chapters_on_the_pus3_shelf_are_about_other_diseases():
    for accession in ("NBK601394", "NBK621299"):
        verdict = assess(PUS3, title="Clinical Characteristics", bookshelf=accession, genereviews=INDEX)
        assert verdict.verdict == MISMATCH and "PUS3" in verdict.reason


def test_genereviews_chapter_matches_by_gene_or_omim():
    assert assess(MAS, title="Clinical Characteristics", bookshelf="NBK274564", genereviews=INDEX).verdict == MATCH
    assert assess(FD, title="whatever", bookshelf="NBK274564", genereviews=INDEX).verdict == MATCH


def test_an_unnamed_title_is_never_enough_to_remove_a_document():
    assert assess(MAS, title="Precocious Puberty: Types, Pathogenesis and Updated Management").verdict == UNKNOWN
    assert assess(MAS, title="Precocious Puberty", text="McCune-Albright syndrome causes peripheral precocious puberty. In MAS ... McCune Albright ... MAS").verdict == MATCH
    assert assess(NOONAN, title="Clinical Indications for Growth Hormone Therapy", abstract="Children with Noonan syndrome may receive GH.").verdict == MATCH
    assert assess(NOONAN, title="Clinical Indications for Growth Hormone Therapy", text="Growth hormone is used in Turner syndrome and in Prader-Willi syndrome.").verdict == MISMATCH


def test_tokens_are_case_sensitive_whole_words():
    assert count_mentions(FD, "FD lesions; GNAS variants; fdx and gnasx do not count") == 2


def test_shelf_search_keeps_only_bookshelf_chapters_about_the_disease(monkeypatch):
    from backend.executors.guidelines import guideline_shelf_search_executor as se

    monkeypatch.setattr(se, "_esearch_ids", lambda db, term, retmax: ["1", "2", "3"] if db == "books" else [])
    monkeypatch.setattr(se, "_http_get_json", lambda url: {"result": {
        "1": {"accessionid": "NBK601394", "title": "Clinical Characteristics", "book": "gene"},
        "2": {"accessionid": "NBK621299", "title": "Clinical Characteristics", "book": "gene"},
        "3": {"accessionid": "NBK274564", "title": "Clinical Characteristics", "book": "gene"},
    }})
    monkeypatch.setattr(se, "_genereviews_index", lambda: INDEX)
    assert se._book_candidates(PUS3.name, "PUS3") == []
    kept = se._book_candidates("McCune-Albright Syndrome", "GNAS")
    assert [c["bookshelf"] for c in kept] == ["NBK274564"] and kept[0]["title"] == "Fibrous Dysplasia / McCune-Albright Syndrome"


def test_shelf_write_drops_off_disease_documents_even_when_carried_forward(monkeypatch):
    from backend.executors.base import NodeInput
    from backend.executors.guidelines import guideline_shelf_write_executor as we

    class Repo:
        def __init__(self):
            self.written, self.considered = None, None

        def list_source_documents(self, slug):
            from backend.guidelines.models import SourceDocument

            return [SourceDocument(disease_slug=slug, doc_id="NBK601394", role="Reference compendium", title="Clinical Characteristics", authors="", journal="", year="continuously updated", scope="", covers=[], pmid=None, bookshelf="NBK601394", pmcid=None, free_full_text=False, is_new=False, updates_note=None)]

        def replace_source_documents(self, slug, docs):
            self.written = docs

        def replace_considered(self, slug, items):
            self.considered = items

    repo = Repo()
    monkeypatch.setattr(we, "_identity", lambda slug: PUS3)
    monkeypatch.setattr(we, "_genereviews_index", lambda: INDEX)
    monkeypatch.setattr(we, "_enrich_docs_from_pubmed", lambda docs: None)
    context = {"gsb-classify": {"docs": [{"pmid": "12345678", "title": "PUS3 deficiency: a review", "kind": "base_consensus"}], "considered": []}}
    out = asyncio.run(we.GuidelineShelfWriteExecutor(repo=repo).execute(NodeInput(node_config={"node_id": "gsb-write"}, context=context, initial_data={"disease_slug": PUS3.slug})))
    assert out.data["ok"] is True
    assert [d["id"] for d in repo.written] == ["12345678"]
    assert [c["bookshelf"] for c in repo.considered] == ["NBK601394"] and repo.considered[0]["category"] == "off-topic"


# --- the data migration ------------------------------------------------------------------------------------------------


@pytest.fixture
def engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from backend import config as app_config
    from backend.shared.persistence import engine as engine_mod

    monkeypatch.setattr(app_config, "DB_URL", f"sqlite:///{tmp_path / 'shelf.db'}")
    engine_mod.reset_engine_for_tests()
    try:
        yield engine_mod.get_engine()
    finally:
        engine_mod.reset_engine_for_tests()


def test_migration_removes_exactly_the_two_off_disease_chapters(engine):
    from alembic.config import Config

    from alembic import command

    slug = PUS3.slug
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE guideline_source_documents (disease_slug TEXT, doc_id TEXT, role TEXT, title TEXT, PRIMARY KEY (disease_slug, doc_id))"))
        conn.execute(text("CREATE TABLE guideline_shelf_considered (disease_slug TEXT, doc_id TEXT, title TEXT, reason TEXT, category TEXT, considered_at TEXT, PRIMARY KEY (disease_slug, doc_id))"))
        for s, d in ((slug, "NBK601394"), (slug, "NBK621299"), ("fd", "NBK274564"), ("fd", "31196103")):
            conn.execute(text("INSERT INTO guideline_source_documents VALUES (:s, :d, 'r', 't')"), {"s": s, "d": d})
    cfg = Config()
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.stamp(cfg, "d3a71f5c2e88")
    command.upgrade(cfg, "a7d2c9e4f1b3")
    with engine.connect() as conn:
        left = conn.execute(text("SELECT disease_slug, doc_id FROM guideline_source_documents ORDER BY 1, 2")).fetchall()
        considered = conn.execute(text("SELECT doc_id, category FROM guideline_shelf_considered ORDER BY 1")).fetchall()
    assert [tuple(r) for r in left] == [("fd", "31196103"), ("fd", "NBK274564")]
    assert [tuple(r) for r in considered] == [("NBK601394", "off-topic"), ("NBK621299", "off-topic")]


def test_shelf_write_empties_a_shelf_whose_every_document_is_about_another_disease(monkeypatch):
    from backend.executors.base import NodeInput
    from backend.executors.guidelines import guideline_shelf_write_executor as we

    class Repo:
        def __init__(self):
            self.written, self.considered = None, None

        def list_source_documents(self, slug):
            from backend.guidelines.models import SourceDocument

            return [SourceDocument(disease_slug=slug, doc_id="NBK601394", role="Reference compendium", title="Clinical Characteristics", authors="", journal="", year="continuously updated", scope="", covers=[], pmid=None, bookshelf="NBK601394", pmcid=None, free_full_text=False, is_new=False, updates_note=None)]

        def replace_source_documents(self, slug, docs):
            self.written = docs

        def replace_considered(self, slug, items):
            self.considered = items

    repo = Repo()
    monkeypatch.setattr(we, "_identity", lambda slug: PUS3)
    monkeypatch.setattr(we, "_genereviews_index", lambda: INDEX)
    monkeypatch.setattr(we, "_enrich_docs_from_pubmed", lambda docs: None)
    context = {"gsb-classify": {"docs": [{"bookshelf": "NBK621299", "title": "Clinical Characteristics", "kind": "reference_compendium"}], "considered": []}}
    out = asyncio.run(we.GuidelineShelfWriteExecutor(repo=repo).execute(NodeInput(node_config={"node_id": "gsb-write"}, context=context, initial_data={"disease_slug": PUS3.slug})))
    assert out.data["ok"] is False and out.data["docCount"] == 0, out.data
    assert repo.written == []  # the wrong chapters are no longer stored or served
