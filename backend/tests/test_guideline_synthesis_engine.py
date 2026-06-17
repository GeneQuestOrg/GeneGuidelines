"""Tests for the GL-ENGINE synthesis engine (GL-ENGINE-1, deterministic skeleton).

In-memory SQLite + shared metadata (the GL-4 test pattern). No network: the
PubMed abstract fetch is monkeypatched. Covers the repo upsert/replace, the
GuidelineSectionOutput preset validators, the shelf_load + synthesis_writer
executors, and the flow-spec / registry wiring. The full engine run (fork waves
+ live LLM) is verified separately against a running stack.
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
from backend.agents.schemas import PRESET_OUTPUT_SCHEMAS, GuidelineSectionOutput
from backend.executors import EXECUTOR_REGISTRY
from backend.executors.base import NodeInput
from backend.executors.guideline_shelf_load_executor import GuidelineShelfLoadExecutor
from backend.executors.guideline_source_verify_executor import GuidelineSourceVerifyExecutor
from backend.executors.guideline_synthesis_writer_executor import (
    GuidelineSynthesisWriterExecutor,
)
from backend.guidelines.repository import SqlaGuidelinesRepo
from backend.shared.persistence.schema import metadata


@pytest.fixture
def repo() -> SqlaGuidelinesRepo:
    # StaticPool + check_same_thread=False: one shared connection so the in-memory
    # DB is visible from the thread-pool (shelf_load reads via run_in_executor).
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    return SqlaGuidelinesRepo(engine=engine)


def _src_doc(doc_id: str, pmid: str | None) -> dict:
    return {
        "id": doc_id,
        "role": "Base consensus",
        "title": f"Doc {doc_id}",
        "authors": "Author A, Author B",
        "journal": "J Rare Dis",
        "year": 2024,
        "scope": "scope text",
        "covers": ["Diagnosis", "Therapy"],
        "pmid": pmid,
        "freeFullText": True,
    }


def _section_output(sid: str, doc: str, pmid: str) -> dict:
    """A validated GuidelineSectionOutput dict, as a gs-sec-* node would emit."""
    return GuidelineSectionOutput(
        id=sid,
        title="ignored — writer overrides from spec",
        intro=f"Intro for {sid}.",
        paragraphs=[
            {
                "id": f"{sid}-p1",
                "text": "A faithful paragraph drawn from the shelf.",
                "source": {"doc": doc, "loc": "§ X"},
                "citations": [pmid],
            }
        ],
    ).model_dump()


# ── repo upsert (replace) + replace_suggestions ────────────────────────────


def test_upsert_synthesis_replaces_not_duplicates(repo: SqlaGuidelinesRepo) -> None:
    base = {
        "title": "FD v1",
        "version": "Synthesis · 1 source",
        "lastUpdated": "2026-01-01",
        "basedOn": "one",
        "synthDisclaimer": "draft",
        "status": "draft",
        "epistemicLevel": "a",
        "sourceIds": ["d1"],
        "sections": [{"id": "diagnosis", "title": "1. Diagnosis", "intro": "", "paragraphs": []}],
    }
    repo.upsert_synthesis("fd", base)
    # Re-run with new content must overwrite, not raise a PK collision.
    repo.upsert_synthesis("fd", {**base, "title": "FD v2", "sourceIds": ["d1", "d2"]})

    got = repo.get_synthesis("fd")
    assert got is not None
    assert got.title == "FD v2"
    assert got.source_ids == ["d1", "d2"]
    # Other diseases untouched by the replace.
    assert repo.get_synthesis("mas") is None


def test_replace_suggestions_clears_old(repo: SqlaGuidelinesRepo) -> None:
    def sug(sid: str) -> dict:
        return {
            "id": sid,
            "kind": "addition",
            "targetSection": "therapy",
            "sectionLabel": "3. Therapy",
            "title": sid,
            "summary": "s",
            "rationale": "r",
            "evidence": "moderate",
            "gate": "expert",
        }

    repo.replace_suggestions("fd", [sug("a"), sug("b")])
    assert {s.id for s in repo.list_suggestions("fd")} == {"a", "b"}
    # Second run with a smaller set replaces wholesale.
    repo.replace_suggestions("fd", [sug("c")])
    assert {s.id for s in repo.list_suggestions("fd")} == {"c"}


# ── GuidelineSectionOutput preset validators ───────────────────────────────


def test_guideline_section_preset_registered() -> None:
    assert PRESET_OUTPUT_SCHEMAS.get("guideline_section") is GuidelineSectionOutput


def test_section_output_accepts_valid() -> None:
    out = GuidelineSectionOutput(
        id="diagnosis",
        title="1. Diagnosis",
        intro="lead",
        paragraphs=[
            {"id": "p1", "text": "t", "source": {"doc": "d1", "loc": "§A"}, "citations": ["31196103"]}
        ],
    )
    assert out.paragraphs[0].source.doc == "d1"
    assert out.paragraphs[0].citations == ["31196103"]


def test_section_output_rejects_missing_source_doc() -> None:
    with pytest.raises(ValidationError):
        GuidelineSectionOutput(
            id="x", title="x", intro="x",
            paragraphs=[{"id": "p1", "text": "t", "source": {"loc": "§A"}}],
        )


def test_section_output_rejects_non_pmid_citation() -> None:
    with pytest.raises(ValidationError):
        GuidelineSectionOutput(
            id="x", title="x", intro="x",
            paragraphs=[
                {"id": "p1", "text": "t", "source": {"doc": "d1"}, "citations": ["not-a-pmid"]}
            ],
        )


def test_section_output_requires_at_least_one_paragraph() -> None:
    with pytest.raises(ValidationError):
        GuidelineSectionOutput(id="x", title="x", intro="x", paragraphs=[])


# ── shelf_load executor ────────────────────────────────────────────────────


def test_shelf_load_reads_shelf_and_abstracts(repo: SqlaGuidelinesRepo, monkeypatch) -> None:
    repo.insert_source_document("fd", _src_doc("boyce2019", "31196103"), 0)
    repo.insert_source_document("fd", _src_doc("genereviews", None), 1)  # no PMID

    def _fake_fetch(pmids, *, include_abstracts=True):
        assert pmids == ["31196103"]  # only PMID-bearing docs fetched
        return {"articles": [{"pmid": "31196103", "abstract": "An abstract."}]}

    monkeypatch.setattr(
        "backend.tools.pubmed_runtime.fetch_article_details_impl", _fake_fetch
    )

    ex = GuidelineShelfLoadExecutor(repo=repo)
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context={}, initial_data={"disease_slug": "fd"}))
    )
    assert out.data["ok"] is True
    assert out.data["shelf_pmids"] == ["31196103"]
    docs = {d["docId"]: d for d in out.data["shelf_docs"]}
    assert docs["boyce2019"]["abstract"] == "An abstract."
    assert docs["genereviews"]["pmid"] is None
    assert docs["genereviews"]["abstract"] == ""


def test_shelf_load_missing_slug() -> None:
    ex = GuidelineShelfLoadExecutor()
    out = asyncio.run(ex.execute(NodeInput(node_config={}, context={}, initial_data={})))
    assert out.data["ok"] is False
    assert "disease_slug" in out.data["error"].lower()


def test_shelf_load_empty_shelf(repo: SqlaGuidelinesRepo) -> None:
    ex = GuidelineShelfLoadExecutor(repo=repo)
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context={}, initial_data={"disease_slug": "noonan"}))
    )
    assert out.data["ok"] is False
    assert out.data["shelf_docs"] == []


# ── synthesis_writer executor (assembly → GL-4) ────────────────────────────


def test_synthesis_writer_assembles_and_upserts(repo: SqlaGuidelinesRepo) -> None:
    context = {
        "gs-shelf": {"shelf_docs": [{"docId": "boyce2019"}, {"docId": "gun2024"}], "shelf_pmids": ["31196103"]},
        "gs-sec-diagnosis": _section_output("diagnosis", "boyce2019", "31196103"),
        "gs-sec-therapy": _section_output("therapy", "gun2024", "31196103"),
    }
    initial = {
        "disease_slug": "fd",
        "disease_name": "Fibrous Dysplasia",
        "sections": [
            {"id": "diagnosis", "title": "1. Diagnosis"},
            {"id": "therapy", "title": "3. Therapy"},
            {"id": "monitoring", "title": "5. Monitoring"},  # no node output → skipped
        ],
    }
    ex = GuidelineSynthesisWriterExecutor(repo=repo)
    out = asyncio.run(ex.execute(NodeInput(node_config={}, context=context, initial_data=initial)))

    assert out.data["ok"] is True
    assert out.data["sectionCount"] == 2  # monitoring skipped (no output)
    assert out.data["sourceCount"] == 2

    syn = repo.get_synthesis("fd")
    assert syn is not None
    assert syn.epistemic_level == "a"
    assert syn.status == "draft"
    assert syn.source_ids == ["boyce2019", "gun2024"]
    assert [s["id"] for s in syn.sections] == ["diagnosis", "therapy"]
    # Title comes from the spec (stable), not the LLM's section title.
    assert syn.sections[0]["title"] == "1. Diagnosis"
    assert syn.sections[0]["paragraphs"][0]["source"]["doc"] == "boyce2019"


def test_synthesis_writer_is_idempotent(repo: SqlaGuidelinesRepo) -> None:
    context = {
        "gs-shelf": {"shelf_docs": [{"docId": "boyce2019"}]},
        "gs-sec-diagnosis": _section_output("diagnosis", "boyce2019", "31196103"),
    }
    initial = {"disease_slug": "fd", "disease_name": "FD", "sections": [{"id": "diagnosis", "title": "Dx"}]}
    ex = GuidelineSynthesisWriterExecutor(repo=repo)
    asyncio.run(ex.execute(NodeInput(node_config={}, context=context, initial_data=initial)))
    asyncio.run(ex.execute(NodeInput(node_config={}, context=context, initial_data=initial)))  # re-run
    syn = repo.get_synthesis("fd")
    assert syn is not None and len(syn.sections) == 1  # not duplicated


def test_synthesis_writer_drops_paragraph_without_source(repo: SqlaGuidelinesRepo) -> None:
    bad_section = {
        "id": "diagnosis",
        "intro": "x",
        "paragraphs": [
            {"id": "ok", "text": "kept", "source": {"doc": "boyce2019"}},
            {"id": "bad", "text": "dropped", "source": {}},  # no doc → dropped
        ],
    }
    context = {"gs-shelf": {"shelf_docs": [{"docId": "boyce2019"}]}, "gs-sec-diagnosis": bad_section}
    initial = {"disease_slug": "fd", "disease_name": "FD", "sections": [{"id": "diagnosis", "title": "Dx"}]}
    ex = GuidelineSynthesisWriterExecutor(repo=repo)
    asyncio.run(ex.execute(NodeInput(node_config={}, context=context, initial_data=initial)))
    syn = repo.get_synthesis("fd")
    assert syn is not None
    assert [p["id"] for p in syn.sections[0]["paragraphs"]] == ["ok"]


# ── flow spec + registry wiring ────────────────────────────────────────────


def test_executors_registered() -> None:
    assert EXECUTOR_REGISTRY["guideline_shelf_load"] is GuidelineShelfLoadExecutor
    assert EXECUTOR_REGISTRY["guideline_source_verify"] is GuidelineSourceVerifyExecutor
    assert EXECUTOR_REGISTRY["guideline_synthesis_writer"] is GuidelineSynthesisWriterExecutor


def test_flow_spec_is_valid_and_connected() -> None:
    spec_path = (
        Path(__file__).resolve().parent.parent / "flows" / "specs" / "guideline_synthesis.json"
    )
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["flow_key"] == "guideline_synthesis"

    nodes = {n["node_id"]: n for n in spec["nodes"]}
    # Section nodes use the simple-mode preset; shelf/verify/writer are custom executors.
    assert nodes["gs-shelf"]["node_type"] == "guideline_shelf_load"
    assert nodes["gs-srcverify"]["node_type"] == "guideline_source_verify"
    assert nodes["gs-write"]["node_type"] == "guideline_synthesis_writer"
    sec_ids = ("diagnosis", "histopathology", "therapy", "surgery", "monitoring")
    for sid in sec_ids:
        node = nodes[f"gs-sec-{sid}"]
        assert node["node_type"] == "prompt"
        assert node["prompt_mode"] == "simple"
        assert node["output_schema_key"] == "guideline_section"

    # Every edge endpoint is a real node; shelf fans out to all sections, which
    # fan in to the verifier, which feeds the writer.
    for e in spec["edges"]:
        assert e["source_node_id"] in nodes
        assert e["target_node_id"] in nodes
    sec_targets = {e["target_node_id"] for e in spec["edges"] if e["source_node_id"] == "gs-shelf"}
    assert sec_targets == {f"gs-sec-{s}" for s in sec_ids}
    verifier_feeders = {e["source_node_id"] for e in spec["edges"] if e["target_node_id"] == "gs-srcverify"}
    assert verifier_feeders == {f"gs-sec-{s}" for s in sec_ids}
    writer_feeders = {e["source_node_id"] for e in spec["edges"] if e["target_node_id"] == "gs-write"}
    assert writer_feeders == {"gs-srcverify"}


# ── GL-ENGINE-2: source_doc_verify (flags) + writer enforcement ────────────


def test_source_verify_flags_off_shelf_doc_and_citation() -> None:
    context = {
        "gs-shelf": {"shelf_docs": [{"docId": "boyce2019"}], "shelf_pmids": ["31196103"]},
        "gs-sec-diagnosis": {
            "id": "diagnosis",
            "paragraphs": [
                {"id": "ok", "text": "t", "source": {"doc": "boyce2019"}, "citations": ["31196103"]},
                {"id": "bad-doc", "text": "t", "source": {"doc": "ghost2099"}, "citations": []},
                {"id": "bad-cit", "text": "t", "source": {"doc": "boyce2019"}, "citations": ["99999999"]},
            ],
        },
    }
    ex = GuidelineSourceVerifyExecutor()
    out = asyncio.run(ex.execute(NodeInput(node_config={}, context=context, initial_data={})))
    assert out.data["ok"] is True
    assert out.data["issues_found"] is True
    codes = sorted(i["code"] for i in out.data["issues"])
    assert codes == ["citation_not_on_shelf", "source_doc_not_on_shelf"]
    assert out.data["sections_checked"] == 1


def test_source_verify_clean_synthesis_has_no_flags() -> None:
    context = {
        "gs-shelf": {"shelf_docs": [{"docId": "boyce2019"}], "shelf_pmids": ["31196103"]},
        "gs-sec-diagnosis": _section_output("diagnosis", "boyce2019", "31196103"),
    }
    ex = GuidelineSourceVerifyExecutor()
    out = asyncio.run(ex.execute(NodeInput(node_config={}, context=context, initial_data={})))
    assert out.data["issues_found"] is False
    assert out.data["total_flags"] == 0


def test_writer_enforces_shelf_membership(repo: SqlaGuidelinesRepo) -> None:
    section = {
        "id": "diagnosis",
        "intro": "x",
        "paragraphs": [
            {"id": "keep", "text": "kept", "source": {"doc": "boyce2019"}, "citations": ["31196103", "99999999"]},
            {"id": "ghost", "text": "off-shelf", "source": {"doc": "ghost2099"}, "citations": []},
        ],
    }
    context = {
        "gs-shelf": {"shelf_docs": [{"docId": "boyce2019"}], "shelf_pmids": ["31196103"]},
        "gs-sec-diagnosis": section,
    }
    initial = {"disease_slug": "fd", "disease_name": "FD", "sections": [{"id": "diagnosis", "title": "Dx"}]}
    ex = GuidelineSynthesisWriterExecutor(repo=repo)
    out = asyncio.run(ex.execute(NodeInput(node_config={}, context=context, initial_data=initial)))
    # one off-shelf paragraph dropped, one off-shelf citation scrubbed.
    assert out.data["droppedParagraphs"] == 1
    assert out.data["droppedCitations"] == 1

    syn = repo.get_synthesis("fd")
    assert syn is not None
    paras = syn.sections[0]["paragraphs"]
    assert [p["id"] for p in paras] == ["keep"]  # ghost2099 paragraph gone
    assert paras[0]["citations"] == ["31196103"]  # off-shelf PMID scrubbed
