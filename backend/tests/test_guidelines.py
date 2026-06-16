"""Tests for the guidelines layer (GL-4): repo round-trip, seed, service, API.

In-memory SQLite + the shared metadata (the doctor_contributions pattern). No
mocking — real SQL via SQLite, and the seed loaded from the bundled JSON.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import backend.guidelines.orm  # noqa: F401 — registers tables on the shared metadata
from backend.guidelines.api import router as guidelines_router
from backend.guidelines.contracts import SourceDocResponse
from backend.guidelines.deps import provide_guidelines_service
from backend.guidelines.repository import (
    InMemoryGuidelinesRepo,
    SqlaGuidelinesRepo,
)
from backend.guidelines.seed import load_seed_payload, seed_guidelines
from backend.guidelines.service import GuidelinesService
from backend.shared.persistence.schema import metadata


@pytest.fixture
def seeded_repo() -> SqlaGuidelinesRepo:
    engine = create_engine("sqlite://", future=True)
    assert "guideline_synthesis" in metadata.tables
    metadata.create_all(engine)
    repo = SqlaGuidelinesRepo(engine=engine)
    seed_guidelines(repo, load_seed_payload())
    return repo


# ── repo round-trip via the seed ──────────────────────────────────────────


def test_fd_shelf_synthesis_suggestions_signals(seeded_repo: SqlaGuidelinesRepo) -> None:
    docs = seeded_repo.list_source_documents("fd")
    assert [d.doc_id for d in docs] == ["boyce2019", "gun2024", "szymczuk2023", "genereviews"]
    assert docs[1].is_new is True  # gun2024
    assert docs[3].bookshelf == "NBK274564"  # genereviews

    synthesis = seeded_repo.get_synthesis("fd")
    assert synthesis is not None
    assert synthesis.epistemic_level == "a"
    assert len(synthesis.sections) == 5
    assert synthesis.what_to_do_now is not None and len(synthesis.what_to_do_now) == 4

    suggestions = seeded_repo.list_suggestions("fd")
    assert {s.id for s in suggestions} == {"sg-oct", "sg-deno", "sg-gnas"}
    deno = next(s for s in suggestions if s.id == "sg-deno")
    assert deno.kind == "modification"
    assert deno.diff is not None and any(ln["t"] == "del" for ln in deno.diff["lines"])

    signals = seeded_repo.get_synthesis_signals("fd")
    assert set(signals) == {"diagnosis", "histopathology", "therapy", "surgery", "monitoring"}
    assert signals["histopathology"].flags == 1


def test_mas_present_and_unknown_empty(seeded_repo: SqlaGuidelinesRepo) -> None:
    assert len(seeded_repo.list_source_documents("mas")) == 2
    assert seeded_repo.get_synthesis("mas") is not None
    # A disease with no guideline-layer data.
    assert seeded_repo.list_source_documents("noonan") == []
    assert seeded_repo.get_synthesis("noonan") is None
    assert seeded_repo.list_suggestions("noonan") == []
    assert seeded_repo.get_synthesis_signals("noonan") == {}


def test_seed_is_idempotent(seeded_repo: SqlaGuidelinesRepo) -> None:
    from backend.guidelines.seed import seed_guidelines_if_empty

    # Already seeded by the fixture → a second run is a no-op.
    assert seed_guidelines_if_empty(seeded_repo) is False


# ── contract casing (must match the frozen camelCase FE types) ─────────────


def test_source_doc_response_is_camelcase(seeded_repo: SqlaGuidelinesRepo) -> None:
    doc = next(d for d in seeded_repo.list_source_documents("fd") if d.doc_id == "gun2024")
    payload = SourceDocResponse.from_domain(doc).model_dump()
    assert payload["isNew"] is True
    assert payload["updatesNote"]
    assert payload["year"] == 2024  # numeric year stays numeric
    assert "is_new" not in payload  # snake_case must not leak


# ── service slug-normalisation ─────────────────────────────────────────────


def test_service_normalises_and_degrades() -> None:
    service = GuidelinesService(repo=InMemoryGuidelinesRepo())
    assert service.list_source_documents("../evil") == []
    assert service.get_synthesis("bad slug") is None
    assert service.get_synthesis_signals("unknown") == {}


# ── API surface (minimal app + InMemory override) ──────────────────────────


def _client_with(repo: InMemoryGuidelinesRepo) -> TestClient:
    app = FastAPI()
    app.include_router(guidelines_router, prefix="/api")
    app.dependency_overrides[provide_guidelines_service] = lambda: GuidelinesService(repo=repo)
    return TestClient(app)


def test_api_endpoints(seeded_repo: SqlaGuidelinesRepo) -> None:
    # Re-use the seeded SQLite data through an InMemory mirror for the API test.
    mem = InMemoryGuidelinesRepo()
    mem.source_documents["fd"] = seeded_repo.list_source_documents("fd")
    mem.synthesis["fd"] = seeded_repo.get_synthesis("fd")  # type: ignore[assignment]
    mem.suggestions["fd"] = seeded_repo.list_suggestions("fd")
    mem.signals["fd"] = seeded_repo.get_synthesis_signals("fd")
    client = _client_with(mem)

    shelf = client.get("/api/diseases/fd/source-documents")
    assert shelf.status_code == 200
    assert shelf.json()[0]["id"] == "boyce2019"
    assert "freeFullText" in shelf.json()[0]

    syn = client.get("/api/diseases/fd/guideline-synthesis")
    assert syn.status_code == 200
    body = syn.json()
    assert body["slug"] == "fd" and body["synthDisclaimer"] and len(body["sections"]) == 5

    sug = client.get("/api/diseases/fd/guideline-suggestions")
    assert sug.status_code == 200 and len(sug.json()) == 3

    sig = client.get("/api/diseases/fd/synthesis-signals")
    assert sig.status_code == 200 and sig.json()["histopathology"]["flags"] == 1

    # No data → empty lists/map (200), synthesis → 404.
    assert client.get("/api/diseases/noonan/source-documents").json() == []
    assert client.get("/api/diseases/noonan/synthesis-signals").json() == {}
    assert client.get("/api/diseases/noonan/guideline-synthesis").status_code == 404
