"""Phase 2 of the guideline-points block: storage, the job (after synthesis and as a backfill), the API and the crawler page. Models and network are faked."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.guidelines.orm  # noqa: F401 — registers the tables
from backend.guidelines.orm import SourceDocumentRow
from backend.guidelines.points import store
from backend.guidelines.relevance import identity_from_disease
from backend.services import guideline_points_job as job
from backend.shared.persistence.schema import metadata
from backend.tests.test_guideline_points import CONSENSUS, GOOD, NO_GAPS, FakeCaller, _draft, _verdicts

MAS = identity_from_disease({"slug": "mas", "name": "McCune-Albright Syndrome", "nameShort": "MAS", "omim": "174800", "gene": "GNAS"})


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata.create_all(eng)
    with Session(eng) as session, session.begin():
        session.add(SourceDocumentRow(disease_slug="mas", doc_id="31196103", role="Base consensus", title="Best practice management guidelines", authors="Javaid MK", journal="Orphanet J Rare Dis", year="2019", scope="", pmid="31196103"))
    return eng


@pytest.fixture
def offline(monkeypatch):
    """No catalog, no NCBI: the disease identity and the shelf's documents are handed in."""
    monkeypatch.setattr("backend.guidelines.relevance.identity_for_slug", lambda slug: MAS)
    monkeypatch.setattr("backend.guidelines.points.sources.load_shelf_documents", lambda shelf, **kw: [CONSENSUS])
    monkeypatch.setattr("backend.tools.genereviews_index.load_index", lambda *a, **k: {})


def _callers():
    gen = FakeCaller([_draft(GOOD)])
    ver = FakeCaller([NO_GAPS, _verdicts(("p1", "PASS", []), ("p2", "PASS", []), ("p3", "PASS", []))])
    return gen, ver, "fake models"


def test_job_stores_a_published_block_and_skips_an_unchanged_shelf(engine, offline):
    gen, ver, models = _callers()
    result = asyncio.run(job.run_guideline_points("mas", callers=(gen, ver, models), engine=engine))
    assert result["status"] == "stored" and result["publish"] is True and result["points"] == 3
    block = store.published_block("mas", engine)
    assert block["title_en"].startswith("What the guideline says") and len(block["points"]) == 3
    assert "<worked_example>" in gen.calls[0]["system"]  # every disease but FD gets the hand-written example
    again = asyncio.run(job.run_guideline_points("mas", callers=_callers(), engine=engine))
    assert again["status"] == "unchanged"
    forced = asyncio.run(job.run_guideline_points("mas", force=True, callers=_callers(), engine=engine))
    assert forced["status"] == "stored"


def test_a_block_that_does_not_publish_is_stored_but_never_served(engine, offline):
    gen = FakeCaller([_draft(GOOD[:2])])
    ver = FakeCaller([NO_GAPS, _verdicts(("p1", "PASS", []), ("p2", "PASS", []))])
    result = asyncio.run(job.run_guideline_points("mas", callers=(gen, ver, "m"), engine=engine))
    assert result["publish"] is False
    assert store.get_points("mas", engine).publish == 0 and store.published_block("mas", engine) is None


def test_fd_keeps_its_hand_written_block():
    assert asyncio.run(job.run_guideline_points("fd"))["status"] == "skipped"


def test_shelf_hash_changes_with_the_shelf(engine):
    from backend.guidelines.repository import SqlaGuidelinesRepo

    shelf = SqlaGuidelinesRepo(engine=engine).list_source_documents("mas")
    assert store.shelf_hash(shelf) == store.shelf_hash(list(shelf))
    assert store.shelf_hash(shelf) != store.shelf_hash(shelf[:0])


def test_backfill_runs_each_disease_and_survives_one_failure(monkeypatch):
    calls = []

    async def fake(slug, force=False):
        calls.append(slug)
        if slug == "bad":
            raise RuntimeError("boom")
        return {"slug": slug, "status": "stored"}

    monkeypatch.setattr(job, "run_guideline_points", fake)
    results = asyncio.run(job.backfill(["fop", "bad", "noonan"]))
    assert calls == ["fop", "bad", "noonan"] and results[1]["status"] == "error" and results[2]["status"] == "stored"


def test_points_run_after_a_synthesis_only(monkeypatch):
    from backend.routers import agent

    ran = []

    async def fake(slug, force=False):
        ran.append(slug)
        return {}

    monkeypatch.setattr("backend.services.guideline_points_job.run_guideline_points", fake)

    async def go():
        await agent._maybe_points_after_synthesis("e1", {"flow_key": "guideline_synthesis", "disease_initial": {"disease_slug": "fop"}})
        await agent._maybe_points_after_synthesis("e2", {"flow_key": "guideline_shelf_build", "disease_initial": {"disease_slug": "fop"}})
        await agent._maybe_points_after_synthesis("e3", {"flow_key": "guideline_synthesis", "error": "x", "disease_initial": {"disease_slug": "mas"}})
        await asyncio.gather(*list(agent._POINTS_TASKS))

    asyncio.run(go())
    assert ran == ["fop"]


def test_api_serves_only_a_published_block(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.guidelines.orm import GuidelinePointsRow
    from backend.guidelines.points.block import published_block
    from backend.main import app

    block = published_block({"publish": True, "accepted": [p.model_dump() for p in GOOD]}, [CONSENSUS])
    rows = {
        "fop": GuidelinePointsRow(disease_slug="fop", publish=1, reason="ok", shelf_hash="h", block=block, record={}, models="m", cost_usd="0.5", generated_at="2026-11-24T00:00:00+00:00"),
        "stargardt-disease": GuidelinePointsRow(disease_slug="stargardt-disease", publish=0, reason="only 2", shelf_hash="h", block=None, record={}, models="m", cost_usd="0.5", generated_at=""),
    }
    monkeypatch.setattr(store, "get_points", lambda slug, engine=None: rows.get(slug))
    client = TestClient(app)
    ok = client.get("/api/diseases/fop/guideline-points")
    assert ok.status_code == 200
    body = ok.json()
    assert body["titlePl"].startswith("Co mówi wytyczna") and body["noticeEn"].startswith("Generated by AI") and len(body["points"]) == 3
    assert body["points"][0]["docUrl"] == "https://pubmed.ncbi.nlm.nih.gov/31196103/"
    assert client.get("/api/diseases/stargardt-disease/guideline-points").status_code == 404
    assert client.get("/api/diseases/noonan/guideline-points").status_code == 404


def test_crawler_page_carries_the_block_in_its_language():
    from backend.content.models import Disease
    from backend.guidelines.points.block import published_block
    from backend.seo import pages

    block = published_block({"publish": True, "accepted": [p.model_dump() for p in GOOD]}, [CONSENSUS])
    disease = Disease(slug="fop", name="Fibrodysplasia Ossificans Progressiva", name_short="FOP", omim="135100", gene="ACVR1", inheritance="", summary="", prevalence_text="", status="", coverage="full", accent="teal")
    labels = {"factGene": "Gene", "factOmim": "OMIM", "factInheritance": "Inheritance", "factPrevalence": "Prevalence", "doctorsCount": "{{count}} doctors", "trialsCount": "{{count}} trials", "linkGuidelines": "g", "doctorsForTitle": "{{disease}}", "trialsForTitle": "{{disease}}", "footerDesc": "f", "notListed": "n", "hubDescription": "{{disease}}", "titleSuffix": "", "linkDiseases": "d", "linkAllDoctors": "a", "linkAbout": "b"}
    pl = pages.disease_hub(disease, labels, "pl", block).body
    en = pages.disease_hub(disease, labels, "en", block).body
    assert "Co mówi wytyczna o rozpoznaniu" in pl and "Wygenerowane przez AI" in pl and "<blockquote" in pl
    assert "What the guideline says about diagnosis" in en and "nobody has approved it" in en
    assert "ggp-points" not in pages.disease_hub(disease, labels, "en", None).body


# --- review fixes (2026-11-24): failures keep a live block, unpublished runs retry --------------------------------------


def test_a_failed_verifier_call_keeps_the_published_block(engine, offline):
    asyncio.run(job.run_guideline_points("mas", callers=_callers(), engine=engine))
    assert store.published_block("mas", engine) is not None
    gen = FakeCaller([_draft(GOOD), None])  # the draft, then a revision call that fails too
    ver = FakeCaller([NO_GAPS, None])  # the coverage review answers, the verifier call fails
    result = asyncio.run(job.run_guideline_points("mas", force=True, callers=(gen, ver, "m"), engine=engine))
    assert result["status"] == "failed"
    assert store.published_block("mas", engine) is not None and len(store.published_block("mas", engine)["points"]) == 3


def test_an_unpublished_run_records_no_shelf_so_the_next_run_tries_again(engine, offline):
    gen = FakeCaller([_draft(GOOD[:2])])
    ver = FakeCaller([NO_GAPS, _verdicts(("p1", "PASS", []), ("p2", "PASS", []))])
    asyncio.run(job.run_guideline_points("mas", callers=(gen, ver, "m"), engine=engine))
    assert store.get_points("mas", engine).shelf_hash == ""
    again = asyncio.run(job.run_guideline_points("mas", callers=_callers(), engine=engine))
    assert again["status"] == "stored" and again["publish"] is True


def test_a_run_already_in_progress_for_the_disease_is_not_started_twice(engine, offline):
    job._RUNNING.add("mas")
    try:
        result = asyncio.run(job.run_guideline_points("mas", callers=_callers(), engine=engine))
    finally:
        job._RUNNING.discard("mas")
    assert result["status"] == "skipped" and "in progress" in result["reason"]


def test_no_run_starts_while_the_monthly_budget_is_used_up(engine, offline, monkeypatch):
    monkeypatch.setattr("backend.research_queue.token_budget.budget_block_reason", lambda **kw: "token_budget")
    gen, ver, models = _callers()
    result = asyncio.run(job.run_guideline_points("mas", callers=(gen, ver, models), engine=engine))
    assert result["status"] == "skipped" and "budget" in result["reason"] and gen.calls == []
