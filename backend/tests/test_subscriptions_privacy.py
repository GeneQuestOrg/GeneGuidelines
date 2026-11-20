"""Subscriptions after the 2026-11-20 privacy review: no lookup by email, every email can unsubscribe, unsubscribing deletes, the community consent is separate, and the only alert sent is "the summary changed"."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.content.service import DiseaseService
from backend.executors.base import NodeInput
from backend.executors.guidelines.guideline_synthesis_writer_executor import GuidelineSynthesisWriterExecutor
from backend.main import app
from backend.subscriptions import email as sub_email
from backend.subscriptions.deps import provide_subscription_service
from backend.subscriptions.models import AlertPrefs
from backend.subscriptions.notify import summary_changed, summary_fingerprint
from backend.subscriptions.repository import InMemorySubscriptionRepo, _prefs_to_json, subscription_from_row
from backend.subscriptions.service import SubscriptionService, hash_client_ref

REF = "browser-ref-abcdef0123456789"


@pytest.fixture
def repo() -> InMemorySubscriptionRepo:
    return InMemorySubscriptionRepo()


@pytest.fixture
def service(repo: InMemorySubscriptionRepo, monkeypatch: pytest.MonkeyPatch) -> SubscriptionService:
    diseases = MagicMock(spec=DiseaseService)
    diseases.get.return_value = SimpleNamespace(name="Fibrous Dysplasia")
    monkeypatch.setattr("backend.subscriptions.service.send_confirmation_email", lambda **kw: False)
    return SubscriptionService(repo=repo, disease_service=diseases)


@pytest.fixture
def client(service: SubscriptionService) -> TestClient:
    app.dependency_overrides[provide_subscription_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.pop(provide_subscription_service, None)


def _subscribe(client: TestClient, email: str, ref: str = REF, community: bool = False) -> str:
    body = client.post(
        "/api/diseases/fd/subscriptions",
        json={"email": email, "client_ref": ref, "community": community},
    ).json()
    return body["dev_confirm_url"].split("token=")[-1]


def test_status_cannot_be_asked_by_email(client: TestClient) -> None:
    _subscribe(client, "parent@example.com")
    assert client.get("/api/diseases/fd/subscriptions/status?email=parent@example.com").status_code == 422
    assert client.get(f"/api/diseases/fd/subscriptions/status?ref={REF}").json() == {"status": "pending"}
    assert client.get("/api/diseases/fd/subscriptions/status?ref=someone-elses-ref-000").json() == {"status": None}


def test_only_the_hash_of_the_browser_reference_is_kept(service: SubscriptionService, repo: InMemorySubscriptionRepo) -> None:
    result = service.subscribe(disease_slug="fd", email="p@example.com", prefs=AlertPrefs(), radius_km=None, client_ref=REF)
    assert result is not None
    assert result.subscription.client_ref_hash == hash_client_ref(REF) != REF
    row = {
        "id": "1", "disease_slug": "fd", "email": "p@example.com", "confirm_token": "t" * 20, "status": "pending",
        "prefs_json": _prefs_to_json(AlertPrefs(community=True), hash_client_ref(REF)), "radius_km": None,
        "created_at": "2026-11-20T00:00:00+00:00", "confirmed_at": None, "unsubscribed_at": None,
    }
    restored = subscription_from_row(row)
    assert restored.client_ref_hash == hash_client_ref(REF)
    assert restored.prefs.community is True
    assert f'"ref": "{hash_client_ref(REF)}"' in row["prefs_json"]  # the Postgres lookup matches this exact text


def test_unsubscribing_deletes_the_address(client: TestClient, repo: InMemorySubscriptionRepo) -> None:
    token = _subscribe(client, "leaver@example.com")
    resp = client.get(f"/api/subscriptions/unsubscribe?token={token}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"].endswith("/diseases/fd?alert=unsubscribed")
    assert repo.get_by_token(token) is None
    assert repo.get_by_slug_email("fd", "leaver@example.com") is None


def test_community_consent_is_separate_and_off_by_default(client: TestClient, repo: InMemorySubscriptionRepo) -> None:
    _subscribe(client, "quiet@example.com", ref="ref-quiet-0123456789")
    _subscribe(client, "helper@example.com", ref="ref-helper-0123456789", community=True)
    assert repo.get_by_slug_email("fd", "quiet@example.com").prefs.community is False
    assert repo.get_by_slug_email("fd", "helper@example.com").prefs.community is True


def test_every_email_carries_an_unsubscribe_link(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[dict] = []
    monkeypatch.setattr(sub_email, "send_email", lambda **kw: sent.append(kw) or True)
    sub_email.send_confirmation_email(to_email="a@b.co", disease_name="FD", disease_slug="fd", confirm_token="tok123")
    sub_email.send_summary_changed_email(to_email="a@b.co", disease_name="FD", disease_slug="fd", unsubscribe_token="tok123")
    for message in sent:
        assert sub_email.build_unsubscribe_url("tok123") in message["text"]
        assert sub_email.build_unsubscribe_url("tok123") in message["html"]
        assert "a@b.co" not in message["purpose"]


def test_summary_changed_goes_to_confirmed_subscribers_only(service: SubscriptionService, monkeypatch: pytest.MonkeyPatch) -> None:
    recipients: list[str] = []
    monkeypatch.setattr("backend.subscriptions.service.send_summary_changed_email", lambda **kw: recipients.append(kw["to_email"]) or True)
    confirmed = service.subscribe(disease_slug="fd", email="yes@example.com", prefs=AlertPrefs(), radius_km=None)
    service.subscribe(disease_slug="fd", email="pending@example.com", prefs=AlertPrefs(), radius_km=None)
    service.confirm(confirmed.subscription.confirm_token)
    assert service.notify_summary_changed(disease_slug="fd", disease_name="Fibrous Dysplasia") == 1
    assert recipients == ["yes@example.com"]


def test_changed_means_the_text_changed() -> None:
    a = [{"id": "dx", "paragraphs": [{"text": "Biopsy is not always needed."}]}]
    b = [{"id": "dx", "paragraphs": [{"text": "Biopsy is not always needed.", "citations": ["123"]}]}]
    c = [{"id": "dx", "paragraphs": [{"text": "GNAS testing confirms the diagnosis."}]}]
    assert summary_fingerprint(a) == summary_fingerprint(b)
    assert not summary_changed(a, b)
    assert summary_changed(a, c)
    assert summary_changed(None, a)


class _SynthRepo:
    def __init__(self, previous_sections):
        self.previous = SimpleNamespace(sections=previous_sections) if previous_sections is not None else None
        self.written = None

    def get_synthesis(self, slug):
        return self.previous

    def upsert_synthesis(self, slug, synthesis):
        self.written = synthesis


def _run_writer(repo: _SynthRepo, calls: list) -> dict:
    initial = {"disease_slug": "fd", "disease_name": "Fibrous Dysplasia", "sections": [{"id": "diagnosis", "title": "Diagnosis"}]}
    context = {
        "initial": initial,
        "gs-shelf": {"shelf_docs": [{"docId": "doc-1"}]},
        "gs-sec-diagnosis": {
            "intro": "",
            "paragraphs": [{"id": "p1", "text": "GNAS testing confirms the diagnosis.", "source": {"doc": "doc-1", "loc": "§ Diagnosis"}, "citations": ["31196103"]}],
        },
    }
    executor = GuidelineSynthesisWriterExecutor(repo=repo, notify=lambda slug, name: calls.append((slug, name)))
    out = asyncio.run(executor.execute(NodeInput(node_config={}, context=context, initial_data=initial)))
    return out.data


def test_writer_notifies_when_the_text_changed_and_not_otherwise() -> None:
    calls: list = []
    first = _run_writer(_SynthRepo(None), calls)
    assert first["ok"] is True, first
    assert calls == [("fd", "Fibrous Dysplasia")]

    calls.clear()
    repo = _SynthRepo(None)
    _run_writer(repo, [])
    _run_writer(_SynthRepo(repo.written["sections"]), calls)
    assert calls == []
