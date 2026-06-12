"""RES-1 — bootstrap admission goes through the fair-share queue.

We do not have Postgres in the sandbox, so the DB touchpoints of the
``/bootstrap-disease`` handler (disease lookup + insert + catalog update), the
account dependency chain, and the heavy fan-out are stubbed. The whole test
runs inside a single event loop (``httpx.AsyncClient`` + ASGI transport)
because the in-process scheduler binds its ``asyncio.PriorityQueue`` to the
running loop — exactly one long-lived loop in production.

Asserted contract:

* a fresh bootstrap returns ``queued`` + ``execution_id`` + ``listed: false``
  + a queue position,
* a shared anonymous bucket (no ``X-Anon-Session``) caps at 3 unfinished jobs;
  the 4th is HTTP 409 with a friendly message (NOT 429),
* distinct anon sessions do not share the cap,
* the rate limiter is gone — no 429 on this path.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.account.deps import provide_account_service, provide_user_repo
from backend.account.repository import InMemoryUserRepo
from backend.account.service import AccountService
from backend.research_queue import get_scheduler, reset_scheduler_for_tests


@pytest.fixture
def app_and_gate(monkeypatch: pytest.MonkeyPatch):
    import backend.routers.pipeline as pipeline
    import backend.services.disease_bootstrap as bootstrap
    from backend.main import app

    monkeypatch.setattr(pipeline, "get_disease_by_slug", lambda *a, **k: None)
    monkeypatch.setattr(
        pipeline, "update_disease_catalog_from_bootstrap", lambda *a, **k: None
    )

    class _FakeConn:
        def cursor(self):
            return self

        def execute(self, *a, **k):
            return None

        def fetchone(self):
            return None

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(pipeline.db, "get_connection", lambda: _FakeConn())

    # The admitted job blocks forever so admitted jobs stay "unfinished" and
    # the anon cap is observable.
    gate = asyncio.Event()

    async def _never_finishes(*a, **k):
        await gate.wait()

    monkeypatch.setattr(bootstrap, "bootstrap_disease_research", _never_finishes)

    user_repo = InMemoryUserRepo()
    account_service = AccountService(repo=user_repo, superadmin_emails=frozenset())
    app.dependency_overrides[provide_user_repo] = lambda: user_repo
    app.dependency_overrides[provide_account_service] = lambda: account_service

    monkeypatch.setenv("RESEARCH_QUEUE_MAX_CONCURRENT", "1")
    monkeypatch.setenv("RESEARCH_QUEUE_ANON_MAX_PENDING", "3")
    reset_scheduler_for_tests()

    yield app, gate

    app.dependency_overrides.pop(provide_user_repo, None)
    app.dependency_overrides.pop(provide_account_service, None)
    reset_scheduler_for_tests()


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def _body(slug: str) -> dict:
    return {"slug": slug, "name": f"Disease {slug}"}


@pytest.mark.asyncio
async def test_bootstrap_returns_queued_status(app_and_gate) -> None:
    app, gate = app_and_gate
    async with _client(app) as client:
        resp = await client.post("/api/pipeline/bootstrap-disease", json=_body("dx1"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["listed"] is False
    assert body["execution_id"]
    assert body["queue_position"] is not None
    await get_scheduler().shutdown()
    gate.set()


@pytest.mark.asyncio
async def test_anonymous_bucket_capped_at_three_then_409(app_and_gate) -> None:
    app, gate = app_and_gate
    async with _client(app) as client:
        for i in range(3):
            r = await client.post(
                "/api/pipeline/bootstrap-disease", json=_body(f"dx{i}")
            )
            assert r.status_code == 200, (i, r.text)
        r4 = await client.post("/api/pipeline/bootstrap-disease", json=_body("dx3"))
    assert r4.status_code == 409, r4.text
    assert r4.status_code != 429
    assert "3 runs" in r4.json()["detail"]
    await get_scheduler().shutdown()
    gate.set()


@pytest.mark.asyncio
async def test_distinct_anon_sessions_do_not_share_cap(app_and_gate) -> None:
    app, gate = app_and_gate
    headers_a = {"X-Anon-Session": "sess-a"}
    headers_b = {"X-Anon-Session": "sess-b"}
    async with _client(app) as client:
        for i in range(3):
            r = await client.post(
                "/api/pipeline/bootstrap-disease",
                json=_body(f"a{i}"),
                headers=headers_a,
            )
            assert r.status_code == 200, r.text
        r_b = await client.post(
            "/api/pipeline/bootstrap-disease", json=_body("b0"), headers=headers_b
        )
        assert r_b.status_code == 200, r_b.text
        r_a = await client.post(
            "/api/pipeline/bootstrap-disease", json=_body("a9"), headers=headers_a
        )
    assert r_a.status_code == 409, r_a.text
    await get_scheduler().shutdown()
    gate.set()
