"""Storing and serving the guideline-points block: the service (after a synthesis and as a backfill), the repository, the run lock, the API and the crawler page. Models and network are faked and passed in through the service's constructor."""

from __future__ import annotations

import asyncio
import hashlib
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.guidelines.orm  # noqa: F401 — registers the tables
from backend.guidelines.orm import SourceDocumentRow
from backend.guidelines.points.block import build_published_block
from backend.guidelines.points.loop import run_loop_pipeline
from backend.guidelines.points.models import BlockOutcome, BlockRecord, shelf_hash
from backend.guidelines.points.repository import (
    InMemoryGuidelinePointsRepo,
    SqlaGuidelinePointsRepo,
    StoredPoints,
    published_block,
)
from backend.guidelines.points.run_lock import InProcessRunLock, PostgresRunLock
from backend.guidelines.points.service import Generation, PointsService, RunGuards, ShelfReader
from backend.guidelines.relevance import identity_from_disease
from backend.guidelines.repository import SqlaGuidelinesRepo
from backend.shared.persistence.schema import metadata
from backend.tests.test_guideline_points import CONSENSUS, GOOD, NO_GAPS, FakeCaller, _draft, _verdicts


class BlockRecordProbe(BaseModel):
    answer: str


MAS = identity_from_disease({"slug": "mas", "name": "McCune-Albright Syndrome", "nameShort": "MAS", "omim": "174800", "gene": "GNAS"})


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata.create_all(eng)
    with Session(eng) as session, session.begin():
        session.add(SourceDocumentRow(disease_slug="mas", doc_id="31196103", role="Base consensus", title="Best practice management guidelines", authors="Javaid MK", journal="Orphanet J Rare Dis", year="2019", scope="", pmid="31196103"))
    return eng


def _callers():
    gen = FakeCaller([_draft(GOOD)])
    ver = FakeCaller([NO_GAPS, _verdicts(("p1", "PASS", []), ("p2", "PASS", []), ("p3", "PASS", []))])
    return gen, ver, "fake models"


class Harness:
    """A service over a real (SQLite) shelf and repository, with no catalog, no NCBI and scripted models: each run takes the next scripted callers."""

    def __init__(self, engine, budget_block_reason=lambda: None, lock=None):
        self.repo = SqlaGuidelinePointsRepo(engine)
        self.callers: list = []
        self.docs = [CONSENSUS]
        self.service = PointsService(
            repo=self.repo,
            reader=ShelfReader(
                list_shelf=SqlaGuidelinesRepo(engine=engine).list_source_documents,
                identity_for=lambda slug: MAS,
                load_index=dict,
                load_documents=lambda shelf, index: list(self.docs),
            ),
            generation=Generation(pipeline=run_loop_pipeline, make_callers=lambda slug, execution_id: self.callers.pop(0)),
            guards=RunGuards(lock=lock or InProcessRunLock(), budget_block_reason=budget_block_reason),
        )

    def run(self, callers, *, force=False):
        self.callers.append(callers)
        return asyncio.run(self.service.run("mas", force=force))


def test_a_published_block_is_stored_and_an_unchanged_shelf_is_skipped(engine):
    h = Harness(engine)
    gen, ver, models = _callers()
    result = h.run((gen, ver, models))
    assert result["status"] == "stored" and result["publish"] is True and result["points"] == 3
    block = published_block("mas", h.repo)
    assert block["title_en"].startswith("What the guideline says") and len(block["points"]) == 3
    assert "<worked_example>" in gen.calls[0]["system"]  # every disease but FD gets the hand-written example
    assert h.repo.get("mas").record["pipeline"] == "loop-1"
    h.callers.clear()
    assert asyncio.run(h.service.run("mas"))["status"] == "unchanged"
    assert h.run(_callers(), force=True)["status"] == "stored"


def test_a_block_that_does_not_publish_is_stored_but_never_served(engine):
    h = Harness(engine)
    gen = FakeCaller([_draft(GOOD[:2])])
    ver = FakeCaller([NO_GAPS, _verdicts(("p1", "PASS", []), ("p2", "PASS", []))])
    assert h.run((gen, ver, "m"))["publish"] is False
    assert h.repo.get("mas").publish is False and published_block("mas", h.repo) is None


def test_fd_keeps_its_hand_written_block(engine):
    assert asyncio.run(Harness(engine).service.run("fd"))["status"] == "skipped"


def test_shelf_hash_changes_with_the_shelf(engine):
    shelf = SqlaGuidelinesRepo(engine=engine).list_source_documents("mas")
    assert shelf_hash(shelf) == shelf_hash(list(shelf))
    assert shelf_hash(shelf) != shelf_hash(shelf[:0])


def test_shelf_hash_is_pinned():
    """Stored blocks record this fingerprint; if it changed, every disease would be rebuilt (and paid for) on its next synthesis."""
    shelf = [
        SimpleNamespace(doc_id="31196103", pmid="31196103", bookshelf=None, pmcid="PMC6567644", title="Best practice management guidelines for fibrous dysplasia/McCune-Albright syndrome"),
        SimpleNamespace(doc_id="NBK274564", pmid=None, bookshelf="NBK274564", pmcid=None, title="Fibrous Dysplasia / McCune-Albright Syndrome"),
    ]
    assert shelf_hash(shelf) == "e4c8cd6dd4313edbef17491232cb70a1ee52730d282b3afdbc2cbfbb195c8487"


def test_backfill_runs_each_disease_and_survives_one_failure(engine):
    h = Harness(engine)
    calls = []

    async def fake(slug, force=False):
        calls.append(slug)
        if slug == "bad":
            raise RuntimeError("boom")
        return {"slug": slug, "status": "stored"}

    h.service.run = fake
    results = asyncio.run(h.service.backfill(["fop", "bad", "noonan"]))
    assert calls == ["fop", "bad", "noonan"] and results[1]["status"] == "error" and results[2]["status"] == "stored"


def test_points_run_after_a_synthesis_only(monkeypatch):
    from backend.routers import agent

    ran = []

    async def fake(slug, force=False):
        ran.append(slug)
        return {}

    monkeypatch.setattr("backend.guidelines.points.deps.default_points_service", lambda: SimpleNamespace(run=fake))

    async def go():
        await agent._maybe_points_after_synthesis("e1", {"flow_key": "guideline_synthesis", "disease_initial": {"disease_slug": "fop"}})
        await agent._maybe_points_after_synthesis("e2", {"flow_key": "guideline_shelf_build", "disease_initial": {"disease_slug": "fop"}})
        await agent._maybe_points_after_synthesis("e3", {"flow_key": "guideline_synthesis", "error": "x", "disease_initial": {"disease_slug": "mas"}})
        await asyncio.gather(*list(agent._POINTS_TASKS))

    asyncio.run(go())
    assert ran == ["fop"]


def test_api_serves_only_a_published_block():
    from fastapi.testclient import TestClient

    from backend.guidelines.points.repository import provide_points_repo
    from backend.main import app

    block = build_published_block({"publish": True, "accepted": [p.model_dump() for p in GOOD]}, [CONSENSUS])
    repo = InMemoryGuidelinePointsRepo({
        "fop": StoredPoints(slug="fop", publish=True, reason="ok", shelf_hash="h", block=block, models="m", cost_usd="0.5", generated_at="2026-11-24T00:00:00+00:00"),
        "stargardt-disease": StoredPoints(slug="stargardt-disease", publish=False, reason="only 2", shelf_hash="h", block=None, models="m", cost_usd="0.5"),
    })
    app.dependency_overrides[provide_points_repo] = lambda: repo
    try:
        client = TestClient(app)
        ok = client.get("/api/diseases/fop/guideline-points")
        assert ok.status_code == 200
        body = ok.json()
        assert body["titlePl"].startswith("Co mówi wytyczna") and body["noticeEn"].startswith("Generated by AI") and len(body["points"]) == 3
        assert body["points"][0]["docUrl"] == "https://pubmed.ncbi.nlm.nih.gov/31196103/"
        assert client.get("/api/diseases/stargardt-disease/guideline-points").status_code == 404
        assert client.get("/api/diseases/noonan/guideline-points").status_code == 404
    finally:
        app.dependency_overrides.pop(provide_points_repo, None)


def test_the_backfill_endpoints_keep_their_urls_and_need_a_superadmin():
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    # The route exists (not 404) and refuses an anonymous caller: 401/403 with Auth0 configured, 503 without it (as in CI).
    assert client.get("/api/pipeline/guideline-points/backfill").status_code in (401, 403, 503)
    assert client.post("/api/pipeline/guideline-points/backfill", json={}).status_code in (401, 403, 503)


def test_crawler_page_carries_the_block_in_its_language():
    from backend.content.models import Disease
    from backend.seo import pages

    block = build_published_block({"publish": True, "accepted": [p.model_dump() for p in GOOD]}, [CONSENSUS])
    disease = Disease(slug="fop", name="Fibrodysplasia Ossificans Progressiva", name_short="FOP", omim="135100", gene="ACVR1", inheritance="", summary="", prevalence_text="", status="", coverage="full", accent="teal")
    labels = {"factGene": "Gene", "factOmim": "OMIM", "factInheritance": "Inheritance", "factPrevalence": "Prevalence", "doctorsCount": "{{count}} doctors", "trialsCount": "{{count}} trials", "linkGuidelines": "g", "doctorsForTitle": "{{disease}}", "trialsForTitle": "{{disease}}", "footerDesc": "f", "notListed": "n", "hubDescription": "{{disease}}", "titleSuffix": "", "linkDiseases": "d", "linkAllDoctors": "a", "linkAbout": "b"}
    pl = pages.disease_hub(disease, labels, "pl", block).body
    en = pages.disease_hub(disease, labels, "en", block).body
    assert "Co mówi wytyczna o rozpoznaniu" in pl and "Wygenerowane przez AI" in pl and "<blockquote" in pl
    assert "What the guideline says about diagnosis" in en and "nobody has approved it" in en
    assert "ggp-points" not in pages.disease_hub(disease, labels, "en", None).body


# --- failures keep a live block, unpublished runs retry -----------------------------------------------------------------


def test_a_failed_verifier_call_keeps_the_published_block(engine):
    h = Harness(engine)
    h.run(_callers())
    assert published_block("mas", h.repo) is not None
    gen = FakeCaller([_draft(GOOD), None])  # the draft, then a revision call that fails too
    ver = FakeCaller([NO_GAPS, None])  # the coverage review answers, the verifier call fails
    result = h.run((gen, ver, "m"), force=True)
    assert result["status"] == "failed"
    assert published_block("mas", h.repo) is not None and len(published_block("mas", h.repo)["points"]) == 3


def test_a_run_with_a_failed_call_never_replaces_a_published_block_even_when_it_publishes(engine):
    h = Harness(engine)
    h.run(_callers())
    before = h.repo.get("mas")
    gen = FakeCaller([_draft(GOOD)])
    ver = FakeCaller([None, _verdicts(("p1", "PASS", []), ("p2", "PASS", []), ("p3", "PASS", []))])  # the coverage call fails, the points pass
    result = h.run((gen, ver, "m"), force=True)
    assert result["status"] == "failed" and "published block stays" in result["reason"]
    after = h.repo.get("mas")
    assert (after.block, after.shelf_hash, after.publish) == (before.block, before.shelf_hash, before.publish)
    assert after.record["attempts"]["count"] == 1  # the attempt is counted on the row, the block is untouched


def test_a_run_with_a_failed_call_that_publishes_a_first_block_records_no_shelf(engine):
    h = Harness(engine)
    gen = FakeCaller([_draft(GOOD)])
    ver = FakeCaller([None, _verdicts(("p1", "PASS", []), ("p2", "PASS", []), ("p3", "PASS", []))])
    assert h.run((gen, ver, "m"))["publish"] is True
    stored = h.repo.get("mas")
    assert stored.published_block is not None and stored.shelf_hash == ""
    assert h.run(_callers())["status"] == "stored"  # the same shelf is tried again, not skipped as unchanged


def test_an_unpublished_run_records_no_shelf_so_the_next_run_tries_again(engine):
    h = Harness(engine)
    gen = FakeCaller([_draft(GOOD[:2])])
    ver = FakeCaller([NO_GAPS, _verdicts(("p1", "PASS", []), ("p2", "PASS", []))])
    h.run((gen, ver, "m"))
    assert h.repo.get("mas").shelf_hash == ""
    again = h.run(_callers())
    assert again["status"] == "stored" and again["publish"] is True


def test_a_run_already_in_progress_for_the_disease_is_not_started_twice(engine):
    h = Harness(engine)
    with h.service.guards.lock.hold("mas"):
        result = h.run(_callers())
    assert result["status"] == "skipped" and "in progress" in result["reason"]


def test_no_run_starts_while_the_monthly_budget_is_used_up(engine):
    h = Harness(engine, budget_block_reason=lambda: "token_budget")
    gen, ver, models = _callers()
    result = h.run((gen, ver, models))
    assert result["status"] == "skipped" and "budget" in result["reason"] and gen.calls == []


# --- the run lock and the typed run record ---------------------------------------------------------------------------


def test_the_postgres_run_lock_falls_back_to_the_process_on_other_databases(engine):
    lock = PostgresRunLock(engine)
    with lock.hold("mas") as first:
        with lock.hold("mas") as second:
            assert first is True and second is False
        with lock.hold("fop") as other:
            assert other is True
    with lock.hold("mas") as again:
        assert again is True


def test_the_advisory_lock_key_is_stable_and_signed_64_bit():
    from backend.guidelines.points.run_lock import _key

    assert _key("mas") == _key("mas") != _key("fop")
    assert -(2**63) <= _key("mas") < 2**63
    assert _key("mas") == int.from_bytes(hashlib.sha256(b"guideline_points:mas").digest()[:8], "big", signed=True)


@pytest.mark.parametrize(
    ("record", "outcome"),
    [
        ({"publish": True, "calls": [{"step": "draft"}], "accepted": [{"id": "p1"}] * 3}, BlockOutcome.PUBLISHED),
        ({"publish": False, "calls": [], "reason": "no readable guideline-grade document"}, BlockOutcome.NO_READABLE_SOURCE),
        ({"publish": False, "calls": [{"step": "draft", "error": {"kind": "api"}}]}, BlockOutcome.CALL_FAILED),
        ({"publish": False, "calls": [{"step": "draft"}], "no_points_reason": "nothing about diagnosis"}, BlockOutcome.NOTHING_SELECTED),
        ({"publish": False, "calls": [{"step": "draft"}], "accepted": [{"id": "p1"}]}, BlockOutcome.TOO_FEW_POINTS),
    ],
)
def test_the_loop_record_is_typed_by_outcome(record, outcome):
    typed = BlockRecord.from_loop(record)
    assert typed.outcome is outcome and typed.pipeline == "loop-1"
    assert typed.clean is (outcome not in (BlockOutcome.CALL_FAILED, BlockOutcome.NO_READABLE_SOURCE))


def test_the_advisory_lock_stops_a_second_process_on_postgres():
    """Two locks with separate in-process state stand for the API and the worker: only one gets the disease."""
    from backend.config import DB_URL as url

    if not url.startswith("postgresql"):
        pytest.skip("needs Postgres (DB_URL)")
    eng = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1), future=True)
    api, worker = PostgresRunLock(eng), PostgresRunLock(eng)
    try:
        with api.hold("lock-test-disease") as first:
            with worker.hold("lock-test-disease") as second:
                assert first is True and second is False
        with worker.hold("lock-test-disease") as after_release:
            assert after_release is True
    finally:
        eng.dispose()


def test_the_published_block_shape_is_the_contract_the_page_reads():
    """The block JSON is what the page and the API response read. Built by today's code and frozen here, so a new pipeline (the bricks) must produce the same shape."""
    import json
    from pathlib import Path

    from backend.guidelines.contracts import GuidelinePointsResponse

    frozen = json.loads((Path(__file__).parent / "fixtures" / "guideline_points_block.json").read_text())
    assert build_published_block({"publish": True, "accepted": [p.model_dump() for p in GOOD]}, [CONSENSUS]) == frozen
    response = GuidelinePointsResponse.from_block(frozen, "2026-11-25T00:00:00+00:00")
    assert len(response.points) == 3 and response.titlePl.startswith("Co mówi")



# --- review fixes (2026-11-25): attempt cap, unreadable sources, the lock inside a run, the backfill endpoint, the loader ---


def test_the_same_shelf_is_tried_at_most_twice_without_a_recorded_result(engine):
    h = Harness(engine)

    def two_points():
        return FakeCaller([_draft(GOOD[:2])]), FakeCaller([NO_GAPS, _verdicts(("p1", "PASS", []), ("p2", "PASS", []))]), "m"

    assert h.run(two_points())["publish"] is False
    assert h.run(two_points())["publish"] is False
    third = h.run(two_points())
    assert third["status"] == "skipped" and "tried 2 times" in third["reason"]
    h.callers.clear()
    assert h.run(_callers(), force=True)["publish"] is True


def test_no_readable_source_never_withdraws_a_published_block(engine):
    h = Harness(engine)
    h.run(_callers())
    before = h.repo.get("mas").published_block
    h.docs = []  # NCBI and Europe PMC down: nothing can be read
    result = h.run(_callers(), force=True)
    assert result["status"] == "failed"
    assert h.repo.get("mas").published_block == before


def test_a_run_skips_while_another_process_holds_the_disease_on_postgres(engine):
    from backend.config import DB_URL as url

    if not url.startswith("postgresql"):
        pytest.skip("needs Postgres (DB_URL)")
    pg = create_engine(url.replace("postgresql://", "postgresql+psycopg://", 1), future=True)
    try:
        h = Harness(engine, lock=PostgresRunLock(pg))
        with PostgresRunLock(pg).hold("mas") as held_elsewhere:
            assert held_elsewhere is True
            result = h.run(_callers())
        assert result["status"] == "skipped" and "in progress" in result["reason"]
        assert h.run(_callers())["status"] == "stored"
    finally:
        pg.dispose()


def test_the_backfill_endpoint_runs_in_the_background_and_reports_through_get(monkeypatch):
    import time

    from fastapi.testclient import TestClient

    from backend.account.deps import require_superadmin
    from backend.guidelines.points import api as points_api
    from backend.main import app

    async def fake_backfill(slugs=None, force=False):
        return [{"slug": s, "status": "stored", "force": force} for s in slugs or ["fop"]]

    monkeypatch.setattr(points_api, "default_points_service", lambda: SimpleNamespace(backfill=fake_backfill))
    monkeypatch.setitem(points_api._POINTS_BACKFILL, "running", False)
    app.dependency_overrides[require_superadmin] = lambda: None
    try:
        with TestClient(app) as client:
            assert client.post("/api/pipeline/guideline-points/backfill", json={"slugs": [" MAS "], "force": True}).json() == {"started": True}
            for _ in range(50):
                state = client.get("/api/pipeline/guideline-points/backfill").json()
                if not state["running"]:
                    break
                time.sleep(0.02)
            assert state == {"running": False, "last": [{"slug": "mas", "status": "stored", "force": True}]}
    finally:
        app.dependency_overrides.pop(require_superadmin, None)


def test_the_loader_grades_and_reads_each_kind_of_document(monkeypatch):
    from backend.guidelines.points import loader

    paragraph = SimpleNamespace(section="Diagnosis", text="x" * 60)
    monkeypatch.setattr(loader, "pubmed_pubtypes", lambda pmids, api_key=None: {"1": ["Practice Guideline"], "2": ["Practice Guideline"], "3": ["Journal Article"], "6": ["Review"]})
    monkeypatch.setattr(loader.pmc_fulltext, "pmid_to_pmcid", lambda pmids, api_key=None: {"1": "PMC1", "6": "PMC6"})

    def pmc(pmcid, api_key=None):
        if pmcid == "PMC6":
            raise TimeoutError("NCBI timed out")
        return [paragraph], "ok", "en", "CC BY"

    monkeypatch.setattr(loader, "fetch_pmc_paragraphs", pmc)
    monkeypatch.setattr(loader, "fetch_bookshelf_paragraphs", lambda accession: ([paragraph], "ok", "GeneReviews terms", "Copyright UW"))
    shelf = [
        SimpleNamespace(doc_id="1", pmid="1", pmcid=None, bookshelf=None, title="Guidelines for X", year="2020", journal="J", authors="A", role="r"),
        SimpleNamespace(doc_id="2", pmid="2", pmcid=None, bookshelf=None, title="Guidelines for X", year="2020", journal="J", authors="A", role="r"),
        SimpleNamespace(doc_id="3", pmid="3", pmcid=None, bookshelf=None, title="A case of X", year="2020", journal="J", authors="A", role="r"),
        SimpleNamespace(doc_id="NBK1", pmid=None, pmcid=None, bookshelf="NBK1", title="old title", year="2021", journal="", authors="", role="r"),
        SimpleNamespace(doc_id="NBK9", pmid=None, pmcid=None, bookshelf="NBK9", title="StatPearls: X", year="2022", journal="", authors="", role="r"),
        SimpleNamespace(doc_id="6", pmid="6", pmcid=None, bookshelf=None, title="X: a review", year="2023", journal="J", authors="A", role="r"),
    ]
    docs = {d.doc_id: d for d in loader.load_shelf_documents(shelf, genereviews={"NBK1": SimpleNamespace(title="X (GeneReviews)")})}
    assert docs["1"].grade == "A" and docs["1"].text_status == "ok" and docs["1"].pmcid == "PMC1" and docs["1"].license == "CC BY"
    assert docs["2"].text_status.startswith("no_pmcid") and not docs["2"].readable
    assert docs["3"].text_status.startswith("not_fetched") and docs["3"].grade == ""
    assert docs["NBK1"].grade == "B" and docs["NBK1"].title == "X (GeneReviews)" and docs["NBK1"].book == "GeneReviews" and docs["NBK1"].copyright == "Copyright UW"
    assert docs["NBK9"].grade == "C" and docs["NBK9"].grade_reason == "Bookshelf chapter outside GeneReviews"
    assert docs["6"].text_status == "unreadable: TimeoutError: NCBI timed out" and not docs["6"].readable


# --- step 4 groundwork: the per-run cost cap and the pipeline switch ------------------------------------------------


def test_the_run_cost_cap_refuses_a_call_and_the_run_is_budget_exceeded(monkeypatch):
    from backend.guidelines.points import llm, service

    budget = llm.LedgerBudget("mas", "e1", cap_usd=0.01)
    monkeypatch.setattr(llm, "record_usage", lambda **kw: None)
    caller = llm.ClaudePointsCaller("anthropic:claude-opus-5-5@high", api_key="test", node_max_tokens=6000, budget=budget, client=SimpleNamespace())
    output, call = asyncio.run(caller.call(role="verifier", system="s", prefix="", user="u", result_type=BlockRecordProbe))
    assert output is None and call["error"]["kind"] == "budget"
    record = BlockRecord.from_loop({"publish": False, "calls": [{"step": "draft", **call}]})
    assert record.outcome is BlockOutcome.BUDGET_EXCEEDED and record.budget_hit and not record.clean
    reports = []
    monkeypatch.setattr(service, "report_limit", lambda limit, message, **tags: reports.append(limit))
    service._report_limits("mas", record)
    assert reports == ["run_cost_cap"]


def test_the_pipeline_comes_from_the_environment(monkeypatch):
    from backend.guidelines.points import deps
    from backend.guidelines.points.loop import run_loop_pipeline

    monkeypatch.delenv("GUIDELINE_POINTS_PIPELINE", raising=False)
    assert deps.selected_pipeline() is run_loop_pipeline
    monkeypatch.setenv("GUIDELINE_POINTS_PIPELINE", "no-such-pipeline")
    assert deps.selected_pipeline() is run_loop_pipeline
