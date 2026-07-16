"""History-mode SPA catch-all (backend/main.py:spa_fallback).

Deep app paths resolve to index.html so history-router links survive a hard
refresh / crawl; unknown API paths still return a JSON 404 (never HTML); real
bundled files are served verbatim with the correct MIME.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def spa_client(tmp_path, monkeypatch):
    """Point the SPA fallback at a throwaway bundle dir and return a client.

    The ``/assets`` mount is registered at import time against the real
    ``/app/static`` (absent under test), so asset requests here exercise the
    catch-all's ``FileResponse`` branch instead — the resulting MIME is the same.
    """
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>GeneGuidelines</title><div id=root></div>",
        encoding="utf-8",
    )
    (tmp_path / "assets" / "index-abc123.js").write_text(
        "console.log('spa');", encoding="utf-8"
    )
    (tmp_path / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n", encoding="utf-8"
    )

    import backend.main as main

    monkeypatch.setattr(main, "_static_dir", tmp_path)
    monkeypatch.setattr(main, "_static_root", tmp_path.resolve())
    # No `with` → skip lifespan/DB startup; the catch-all needs neither.
    return TestClient(main.app)


def test_deep_path_serves_index_html(spa_client: TestClient) -> None:
    for path in ("/diseases/fd", "/about", "/doctors", "/diseases/fd/guidelines"):
        resp = spa_client.get(path)
        assert resp.status_code == 200, path
        assert "text/html" in resp.headers["content-type"], path
        assert "<title>GeneGuidelines</title>" in resp.text, path


def test_root_serves_index_html(spa_client: TestClient) -> None:
    resp = spa_client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_unknown_api_path_returns_json_404_not_html(spa_client: TestClient) -> None:
    resp = spa_client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert "application/json" in resp.headers["content-type"]
    assert "<title>" not in resp.text


def test_real_bundled_file_served_verbatim(spa_client: TestClient) -> None:
    resp = spa_client.get("/robots.txt")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "User-agent" in resp.text


def test_asset_served_with_js_mime(spa_client: TestClient) -> None:
    resp = spa_client.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    ctype = resp.headers["content-type"]
    assert "javascript" in ctype or "ecmascript" in ctype


def test_health_unaffected_by_catch_all(spa_client: TestClient) -> None:
    resp = spa_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
