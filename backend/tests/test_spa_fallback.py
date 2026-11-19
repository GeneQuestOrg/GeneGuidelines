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
    prerendered = tmp_path / "pl" / "diseases" / "fd"
    prerendered.mkdir(parents=True)
    (prerendered / "index.html").write_text(
        "<!doctype html><title>Dysplazja</title><div id=gg-prerender>treść</div>",
        encoding="utf-8",
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


def test_api_prefix_but_not_segment_serves_spa(spa_client: TestClient) -> None:
    # A top-level route that merely *starts with* "api" (e.g. a future "/api-guide"
    # SPA route) must NOT be swallowed by the API 404 guard — only real "api/..."
    # segments are. Guards the startswith("api") -> segment-test hardening.
    for path in ("/api-guide", "/apiary", "/apis"):
        resp = spa_client.get(path)
        assert resp.status_code == 200, path
        assert "text/html" in resp.headers["content-type"], path


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


def test_prerendered_page_wins_over_the_empty_shell(spa_client: TestClient) -> None:
    # The FD pages are written at build time to `<path>/index.html`. The path is a
    # directory, so without the directory-index branch the catch-all would answer
    # with the SPA shell and everything that does not run JavaScript would see a
    # title and nothing else — which is exactly what the live site did.
    resp = spa_client.get("/pl/diseases/fd")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<title>Dysplazja</title>" in resp.text
    assert "gg-prerender" in resp.text


def test_directory_without_an_index_still_falls_back(spa_client: TestClient) -> None:
    # "/pl/diseases" is a directory in the bundle but holds no index.html of its
    # own, so it must keep resolving to the SPA shell rather than 404.
    resp = spa_client.get("/pl/diseases")
    assert resp.status_code == 200
    assert "<title>GeneGuidelines</title>" in resp.text


def test_shell_serves_app_routes_once_home_is_prerendered(spa_client: TestClient, tmp_path) -> None:
    """With the home page prerendered into index.html, only "/" gets it: every other app route gets the shell, which names no canonical URL, so /diseases/mas is not declared a duplicate of the home page."""
    (tmp_path / "index.html").write_text(
        '<!doctype html><title>Home</title><link rel="canonical" href="https://x/"><div id=gg-prerender>home</div>',
        encoding="utf-8",
    )
    (tmp_path / "_shell.html").write_text(
        "<!doctype html><title>GeneGuidelines</title><div id=root></div>", encoding="utf-8"
    )
    assert "gg-prerender" in spa_client.get("/").text
    for path in ("/diseases/mas", "/doctors", "/pl/doctors"):
        resp = spa_client.get(path)
        assert resp.status_code == 200, path
        assert "canonical" not in resp.text, path
        assert "<title>GeneGuidelines</title>" in resp.text, path
    # A prerendered page still wins over the shell.
    assert "Dysplazja" in spa_client.get("/pl/diseases/fd").text
