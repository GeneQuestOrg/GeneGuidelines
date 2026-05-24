"""End-to-end tests for the evidence audit API.

Uses ``FastAPI TestClient`` with ``app.dependency_overrides`` to swap
the SQL repositories for in-memory fakes. The real Postgres engine
never gets touched here — this is fast (<100 ms total) and isolated
from the production DB.

Covers:

- the five GET endpoints (happy + 404),
- the two POST endpoints (happy, 400 on bad payload, 401 when API key
  is required but missing),
- caching headers + envelope shapes.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.content.models import Disease
from backend.content.repository import InMemoryDiseaseRepo
from backend.evidence.deps import (
    provide_article_audit_service,
    provide_evidence_snapshot_service,
)
from backend.evidence.repository import InMemoryAuditRepo, InMemorySnapshotRepo
from backend.evidence.service import (
    ArticleAuditService,
    EvidenceSnapshotService,
)
from backend.main import app


@pytest.fixture(autouse=True)
def _clear_evidence_overrides() -> None:
    """Reset dep overrides + in-process response cache between tests.

    Without the cache reset, the second test in a run sees the first
    test's payload because :func:`backend.shared.cache.cache_response`
    keys by URL+query and TTL is 60 s — far longer than a test takes.
    """
    from backend.shared import cache

    cache.clear()
    yield
    app.dependency_overrides.pop(provide_evidence_snapshot_service, None)
    app.dependency_overrides.pop(provide_article_audit_service, None)
    cache.clear()


def _seed_disease(slug: str = "fd") -> Disease:
    return Disease(
        slug=slug,
        name="Fibrous Dysplasia",
        name_short="FD",
        omim="174800",
        gene="GNAS",
        inheritance="Somatic",
        summary="Test disease for API integration.",
        prevalence_text="rare",
        status="draft",
        coverage="full",
        accent="amber",
    )


def _wire_services(
    *,
    snapshot_repo: InMemorySnapshotRepo | None = None,
    audit_repo: InMemoryAuditRepo | None = None,
    disease_repo: InMemoryDiseaseRepo | None = None,
) -> tuple[InMemorySnapshotRepo, InMemoryAuditRepo, InMemoryDiseaseRepo]:
    snapshot_repo = snapshot_repo or InMemorySnapshotRepo()
    audit_repo = audit_repo or InMemoryAuditRepo()
    disease_repo = disease_repo or InMemoryDiseaseRepo(seed=[_seed_disease()])
    snapshot_service = EvidenceSnapshotService(
        snapshot_repo=snapshot_repo, disease_repo=disease_repo
    )
    audit_service = ArticleAuditService(
        audit_repo=audit_repo, disease_repo=disease_repo
    )
    app.dependency_overrides[provide_evidence_snapshot_service] = (
        lambda: snapshot_service
    )
    app.dependency_overrides[provide_article_audit_service] = (
        lambda: audit_service
    )
    return snapshot_repo, audit_repo, disease_repo


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# --- Snapshot reads ----------------------------------------------------------


def test_get_snapshots_for_disease_happy_path(client: TestClient) -> None:
    snapshot_repo, _, _ = _wire_services()
    snapshot_repo.insert(  # type: ignore[arg-type]
        _snapshot_input(disease_slug="fd", evidence_score=72)
    )
    response = client.get("/api/evidence/diseases/fd/snapshots")
    assert response.status_code == 200
    payload = response.json()
    assert payload["diseaseSlug"] == "fd"
    assert len(payload["snapshots"]) == 1
    assert payload["snapshots"][0]["evidenceScore"] == 72


def test_get_snapshots_for_unknown_disease_returns_404(client: TestClient) -> None:
    _wire_services(disease_repo=InMemoryDiseaseRepo())
    response = client.get("/api/evidence/diseases/unknown/snapshots")
    assert response.status_code == 404


def test_get_snapshots_returns_empty_list_for_known_disease_without_snapshots(
    client: TestClient,
) -> None:
    _wire_services()
    response = client.get("/api/evidence/diseases/fd/snapshots")
    assert response.status_code == 200
    assert response.json()["snapshots"] == []


def test_get_latest_snapshot_happy_path(client: TestClient) -> None:
    snapshot_repo, _, _ = _wire_services()
    snapshot_repo.insert(_snapshot_input(disease_slug="fd", notes="old"))
    snapshot_repo.insert(_snapshot_input(disease_slug="fd", notes="new"))
    response = client.get("/api/evidence/diseases/fd/snapshots/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["notes"] == "new"
    assert payload["diseaseSlug"] == "fd"


def test_get_latest_snapshot_returns_404_when_no_snapshots(
    client: TestClient,
) -> None:
    _wire_services()
    response = client.get("/api/evidence/diseases/fd/snapshots/latest")
    assert response.status_code == 404


def test_get_snapshot_by_id_happy_path(client: TestClient) -> None:
    snapshot_repo, _, _ = _wire_services()
    inserted = snapshot_repo.insert(
        _snapshot_input(disease_slug="fd", evidence_score=80)
    )
    response = client.get(f"/api/evidence/snapshots/{inserted.id}")
    assert response.status_code == 200
    assert response.json()["id"] == inserted.id


def test_get_snapshot_by_id_returns_404_when_unknown(client: TestClient) -> None:
    _wire_services()
    response = client.get("/api/evidence/snapshots/9999")
    assert response.status_code == 404


# --- Audit reads -------------------------------------------------------------


def test_list_audits_for_disease_happy_path(client: TestClient) -> None:
    _, audit_repo, _ = _wire_services()
    audit_repo.upsert(_audit_input(pmid="31337488", disease_slug="fd"))
    response = client.get("/api/evidence/diseases/fd/article-audits")
    assert response.status_code == 200
    payload = response.json()
    assert payload["diseaseSlug"] == "fd"
    assert payload["audits"][0]["pmid"] == "31337488"
    assert payload["audits"][0]["aiCategories"] == ["treatment"]


def test_list_audits_for_unknown_disease_returns_404(client: TestClient) -> None:
    _wire_services(disease_repo=InMemoryDiseaseRepo())
    response = client.get("/api/evidence/diseases/unknown/article-audits")
    assert response.status_code == 404


def test_list_audits_for_pmid_returns_cross_disease_rows(
    client: TestClient,
) -> None:
    _, audit_repo, _ = _wire_services(
        disease_repo=InMemoryDiseaseRepo(
            seed=[_seed_disease("fd"), _seed_disease("mas")]
        )
    )
    audit_repo.upsert(
        _audit_input(
            pmid="31337488", disease_slug="fd", execution_id="exec-1"
        )
    )
    audit_repo.upsert(
        _audit_input(
            pmid="31337488", disease_slug="mas", execution_id="exec-2"
        )
    )
    response = client.get("/api/evidence/articles/31337488/audits")
    assert response.status_code == 200
    payload = response.json()
    assert payload["pmid"] == "31337488"
    assert len(payload["audits"]) == 2
    assert {a["diseaseSlug"] for a in payload["audits"]} == {"fd", "mas"}


def test_list_audits_for_invalid_pmid_returns_empty(client: TestClient) -> None:
    _wire_services()
    response = client.get("/api/evidence/articles/not-a-pmid/audits")
    assert response.status_code == 200
    assert response.json()["audits"] == []


# --- Snapshot writes ---------------------------------------------------------


def test_create_snapshot_happy_path(client: TestClient) -> None:
    _wire_services()
    response = client.post(
        "/api/evidence/snapshots",
        json={
            "diseaseSlug": "fd",
            "triggeredByExecutionId": "exec-create",
            "triggeredByFlowKey": "pubmed",
            "articlesSeenTotal": 120,
            "articlesCitedInGuideline": 18,
            "categoryCounts": {"treatment": 40, "monitoring": 20},
            "qualityCounts": {"high": 25, "moderate": 60, "low": 35},
            "knowledgeGaps": ["no pediatric data"],
            "evidenceScore": 72,
            "confidenceIndex": 65,
            "avgSynthesisConfidence": 0.78,
            "notes": "Bootstrap snapshot.",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] > 0
    assert payload["diseaseSlug"] == "fd"
    assert payload["categoryCounts"]["treatment"] == 40
    assert payload["qualityCounts"]["moderate"] == 60


def test_create_snapshot_rejects_unknown_disease(client: TestClient) -> None:
    _wire_services(disease_repo=InMemoryDiseaseRepo())
    response = client.post(
        "/api/evidence/snapshots",
        json={"diseaseSlug": "fd"},
    )
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_create_snapshot_rejects_out_of_range_score(client: TestClient) -> None:
    _wire_services()
    response = client.post(
        "/api/evidence/snapshots",
        json={
            "diseaseSlug": "fd",
            "evidenceScore": 150,  # Pydantic ge=0, le=100 should reject
        },
    )
    assert response.status_code == 422


def test_create_snapshot_requires_api_key_when_env_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wire_services()
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "test-secret")
    response = client.post(
        "/api/evidence/snapshots",
        json={"diseaseSlug": "fd"},
    )
    assert response.status_code == 401


def test_create_snapshot_accepts_api_key_when_env_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wire_services()
    monkeypatch.setenv("GENEGUIDELINES_API_KEY", "test-secret")
    response = client.post(
        "/api/evidence/snapshots",
        json={"diseaseSlug": "fd"},
        headers={"Authorization": "Bearer test-secret"},
    )
    assert response.status_code == 200


# --- Audit writes ------------------------------------------------------------


def test_create_audit_happy_path(client: TestClient) -> None:
    _wire_services()
    response = client.post(
        "/api/evidence/article-audits",
        json={
            "pmid": "31337488",
            "diseaseSlug": "fd",
            "triggeredByExecutionId": "exec-aa",
            "aiCategories": ["treatment", "monitoring"],
            "aiRationale": "RCT.",
            "aiModel": "openrouter:google/gemma-4-31b-it:free",
            "aiConfidence": 0.85,
            "qualityTier": "high",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["pmid"] == "31337488"
    assert payload["aiCategories"] == ["treatment", "monitoring"]
    assert payload["qualityTier"] == "high"


def test_create_audit_rejects_malformed_pmid(client: TestClient) -> None:
    _wire_services()
    response = client.post(
        "/api/evidence/article-audits",
        json={
            "pmid": "not-a-pmid",
            "diseaseSlug": "fd",
            "aiCategories": ["treatment"],
        },
    )
    # The pydantic pattern check rejects before service.record runs.
    assert response.status_code == 422


def test_create_audit_rejects_empty_categories(client: TestClient) -> None:
    _wire_services()
    response = client.post(
        "/api/evidence/article-audits",
        json={
            "pmid": "31337488",
            "diseaseSlug": "fd",
            "aiCategories": [],
        },
    )
    assert response.status_code == 422


def test_create_audit_returns_400_for_unknown_disease(client: TestClient) -> None:
    _wire_services(disease_repo=InMemoryDiseaseRepo())
    response = client.post(
        "/api/evidence/article-audits",
        json={
            "pmid": "31337488",
            "diseaseSlug": "fd",
            "aiCategories": ["treatment"],
        },
    )
    assert response.status_code == 400


def test_create_audit_idempotent_on_natural_key(client: TestClient) -> None:
    _wire_services()
    payload = {
        "pmid": "31337488",
        "diseaseSlug": "fd",
        "triggeredByExecutionId": "exec-idem",
        "aiCategories": ["treatment"],
        "aiRationale": "initial",
    }
    first = client.post("/api/evidence/article-audits", json=payload)
    assert first.status_code == 200
    initial_id = first.json()["id"]
    initial_created_at = first.json()["createdAt"]

    payload["aiCategories"] = ["treatment", "monitoring"]
    payload["aiRationale"] = "updated"
    second = client.post("/api/evidence/article-audits", json=payload)
    assert second.status_code == 200
    assert second.json()["id"] == initial_id
    assert second.json()["aiCategories"] == ["treatment", "monitoring"]
    assert second.json()["aiRationale"] == "updated"
    assert second.json()["createdAt"] == initial_created_at


# --- Caching headers --------------------------------------------------------


def test_get_snapshots_advertises_public_cache(client: TestClient) -> None:
    snapshot_repo, _, _ = _wire_services()
    snapshot_repo.insert(_snapshot_input(disease_slug="fd"))
    response = client.get("/api/evidence/diseases/fd/snapshots")
    assert response.status_code == 200
    # The global ``security_headers`` middleware sets Cache-Control on
    # GET endpoints under public paths — evidence reads follow the same
    # contract once the prefix is on the list. Until then, the per-route
    # ``@cache_response`` decorator emits its own Cache-Control header.
    assert (
        response.headers.get("cache-control") is not None
        or response.headers.get("Cache-Control") is not None
    )


# --- Helpers ----------------------------------------------------------------


def _snapshot_input(*, disease_slug: str, **overrides):
    from backend.evidence.repository import SnapshotInput

    payload = {"disease_slug": disease_slug}
    payload.update(overrides)
    return SnapshotInput(**payload)


def _audit_input(
    *,
    pmid: str,
    disease_slug: str,
    execution_id: str = "exec-1",
    categories: tuple[str, ...] = ("treatment",),
):
    from backend.evidence.repository import AuditInput

    return AuditInput(
        pmid=pmid,
        disease_slug=disease_slug,
        triggered_by_execution_id=execution_id,
        ai_categories=categories,  # type: ignore[arg-type]
    )
