"""Integration test for ``GET /api/disease-index/suggest``.

Uses FastAPI's ``TestClient`` against the real Postgres engine — same
shape as :mod:`backend.tests.test_content_api`. The fixture seeds the
disease-index tables and the local content tables so the cross-reference
that decides ``hasLocalRecord`` is exercised end-to-end.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from backend.content_db import ensure_content_schema, seed_content_if_empty
    from backend.disease_index.repository import (
        SqlaDiseaseIndexRepo,
        ensure_disease_index_schema,
    )
    from backend.disease_index.seeds import seed_disease_index_if_empty
    from backend.main import app

    ensure_content_schema()
    seed_content_if_empty()
    ensure_disease_index_schema()
    seed_disease_index_if_empty(SqlaDiseaseIndexRepo())
    return TestClient(app)


def test_suggest_marfan_returns_canonical_match(client: TestClient) -> None:
    response = client.get("/api/disease-index/suggest", params={"q": "marfan"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "marfan"
    assert payload["suggestions"], "marfan should match at least one entry"
    top = payload["suggestions"][0]
    assert top["canonicalName"] == "Marfan Syndrome"
    assert top["matchedAlias"]["alias"] == "Marfan Syndrome"
    assert top["isInScope"] is True
    assert top["category"] == "genetic"


def test_suggest_by_gene_returns_disease(client: TestClient) -> None:
    response = client.get("/api/disease-index/suggest", params={"q": "FBN1"})
    assert response.status_code == 200
    suggestions = response.json()["suggestions"]
    assert any(s["canonicalName"] == "Marfan Syndrome" for s in suggestions)


def test_suggest_by_omim_returns_disease(client: TestClient) -> None:
    response = client.get("/api/disease-index/suggest", params={"q": "154700"})
    assert response.status_code == 200
    suggestions = response.json()["suggestions"]
    assert any(s["canonicalName"] == "Marfan Syndrome" for s in suggestions)


def test_suggest_polish_synonym_with_diacritics(client: TestClient) -> None:
    response = client.get(
        "/api/disease-index/suggest", params={"q": "Dysplazja włóknista"}
    )
    assert response.status_code == 200
    suggestions = response.json()["suggestions"]
    assert any(s["canonicalName"] == "Fibrous Dysplasia" for s in suggestions)


def test_suggest_marks_local_record_for_covered_diseases(client: TestClient) -> None:
    """The covered-by-content cross-reference is the autocomplete badge.

    FD has full GeneGuidelines content, so the suggestion must carry
    ``hasLocalRecord: true`` even though the index entry is technically
    independent of the ``diseases`` table.
    """
    response = client.get("/api/disease-index/suggest", params={"q": "fibrous"})
    assert response.status_code == 200
    fd = next(
        s
        for s in response.json()["suggestions"]
        if s["canonicalName"] == "Fibrous Dysplasia"
    )
    assert fd["hasLocalRecord"] is True
    assert fd["localSlug"] == "fd"


def test_suggest_without_match_returns_empty(client: TestClient) -> None:
    response = client.get(
        "/api/disease-index/suggest", params={"q": "xyzzyplugh-not-a-disease"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["suggestions"] == []


def test_suggest_short_query_returns_empty_envelope(client: TestClient) -> None:
    """Empty / single-space queries are not 400 — they just return no hits.

    The frontend hits this endpoint on every keystroke; a 400 on an
    in-progress input would flood the console with red errors. An empty
    list is the right shape.
    """
    response = client.get("/api/disease-index/suggest", params={"q": ""})
    assert response.status_code == 200
    assert response.json() == {"query": "", "suggestions": [], "elapsedMs": 0}


def test_suggest_respects_limit(client: TestClient) -> None:
    """The ``limit`` parameter caps the response size."""
    response = client.get(
        "/api/disease-index/suggest", params={"q": "syndrome", "limit": 3}
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["suggestions"]) <= 3
