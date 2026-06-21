"""Tests for disease alert subscriptions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.content.service import DiseaseService
from backend.main import app
from backend.subscriptions.deps import provide_subscription_service
from backend.subscriptions.models import AlertPrefs
from backend.subscriptions.repository import InMemorySubscriptionRepo
from backend.subscriptions.service import SubscriptionService


@pytest.fixture
def disease_service() -> DiseaseService:
    mock = MagicMock(spec=DiseaseService)
    disease = MagicMock()
    disease.name = "Fibrous Dysplasia"
    mock.get.return_value = disease
    return mock


@pytest.fixture
def subscription_service(disease_service: DiseaseService) -> SubscriptionService:
    return SubscriptionService(
        repo=InMemorySubscriptionRepo(),
        disease_service=disease_service,
    )


@pytest.fixture
def api_client(disease_service: DiseaseService) -> TestClient:
    """API client with in-memory subscription repo (CI Postgres lacks new tables)."""
    service = SubscriptionService(
        repo=InMemorySubscriptionRepo(),
        disease_service=disease_service,
    )
    app.dependency_overrides[provide_subscription_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.pop(provide_subscription_service, None)


def test_subscribe_and_confirm(subscription_service: SubscriptionService) -> None:
    result = subscription_service.subscribe(
        disease_slug="fd",
        email="parent@example.com",
        prefs=AlertPrefs(),
        radius_km=500,
    )
    assert result is not None
    assert result.subscription.status == "pending"
    assert result.dev_confirm_url is not None

    token = result.subscription.confirm_token
    confirmed = subscription_service.confirm(token)
    assert confirmed is not None
    assert confirmed.status == "confirmed"

    status = subscription_service.status(disease_slug="fd", email="parent@example.com")
    assert status == "confirmed"


def test_subscribe_api(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.subscriptions.service.send_confirmation_email",
        lambda **kwargs: False,
    )
    response = api_client.post(
        "/api/diseases/fd/subscriptions",
        json={
            "email": "parent@example.com",
            "prefs": {
                "guidelines": True,
                "trials": True,
                "therapies": False,
                "doctors": True,
            },
            "radius_km": 500,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "pending"
    assert body.get("dev_confirm_url")


def test_confirm_json(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.subscriptions.service.send_confirmation_email",
        lambda **kwargs: False,
    )
    created = api_client.post(
        "/api/diseases/fd/subscriptions",
        json={"email": "other@example.com", "prefs": {}, "radius_km": 100},
    ).json()
    token = created["dev_confirm_url"].split("token=")[-1]
    confirmed = api_client.get(f"/api/subscriptions/confirm.json?token={token}")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
