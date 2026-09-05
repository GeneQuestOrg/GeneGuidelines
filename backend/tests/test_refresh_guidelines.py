"""The refresh script must report what it actually changed.

Its whole value over seven hand-typed curls is the before/after it prints: an HTTP
200 from a trigger endpoint means a run *started*, not that a synthesis was written.
A script that says "done" on the strength of a 200 is worse than no script, because
it turns a silent failure into a confident one.
"""

from __future__ import annotations

import pytest

from backend.scripts import refresh_guidelines as rg


def test_size_counts_paragraph_text_across_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "sections": [
            {"paragraphs": [{"text": "abc"}, {"text": "de"}]},
            {"paragraphs": [{"text": "fghi"}]},
        ]
    }
    monkeypatch.setattr(rg, "_request", lambda url, key: payload)

    assert rg._synthesis_size("https://x", "fd") == (9, 2)


def test_a_disease_with_no_synthesis_reads_as_zero_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A disease that has never been synthesised is the normal starting state."""

    def _404(url: str, key: str):
        raise SystemExit("HTTP 404")

    monkeypatch.setattr(rg, "_request", _404)

    assert rg._synthesis_size("https://x", "brand-new") == (0, 0)


def test_empty_sections_do_not_inflate_the_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """Five padded-but-empty sections must not read as a healthy synthesis — that is
    exactly the shape the gemma regression produced on production."""
    monkeypatch.setattr(
        rg, "_request", lambda url, key: {"sections": [{"paragraphs": []} for _ in range(5)]}
    )

    assert rg._synthesis_size("https://x", "fd") == (0, 5)


def test_a_run_that_reports_an_error_is_not_counted_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rg, "_POLL_EVERY_SEC", 0)
    monkeypatch.setattr(rg, "_request", lambda url, key: {"done": True, "error": "boom"})

    assert rg._wait("https://x", "exec-1", "synthesis") is False


def test_a_finished_run_is_counted_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rg, "_POLL_EVERY_SEC", 0)
    monkeypatch.setattr(rg, "_request", lambda url, key: {"done": True, "error": None})

    assert rg._wait("https://x", "exec-1", "synthesis") is True


def test_a_trigger_without_an_execution_id_fails_loudly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No execution_id means nothing to poll — silently moving on would leave the
    disease unrefreshed while the summary line claimed otherwise."""
    monkeypatch.setattr(rg, "_request", lambda url, key, method="GET": {"detail": "nope"})

    assert rg._run_flow("https://x", "k", "fd", "guideline-shelf", "shelf") is False


def test_the_paths_the_script_calls_are_routes_the_app_actually_serves() -> None:
    """A wrong prefix here fails as 405, not 404, which reads like a bug in the app.

    The trigger endpoints sit behind the pipeline router's prefix and the read
    endpoints do not. Reading the `@router.post` decorator alone misses that — the
    prefix is applied at include_router — and the un-prefixed path still matches the
    SPA catch-all, so the script got "Method Not Allowed" against a URL that simply
    does not exist. Checked against the app's route table rather than a copy of it.
    """
    from backend.main import app

    routes = {
        (getattr(r, "path", None), method)
        for r in app.routes
        for method in (getattr(r, "methods", None) or set())
    }

    expected = [
        (rg._TRIGGER_PATH.replace("{flow}", "guideline-synthesis"), "POST"),
        (rg._TRIGGER_PATH.replace("{flow}", "guideline-shelf"), "POST"),
        (rg._STATUS_PATH, "GET"),
        (rg._SYNTHESIS_PATH, "GET"),
        (rg._CATALOG_PATH, "GET"),
    ]
    missing = [pair for pair in expected if pair not in routes]

    assert not missing, f"the script calls URLs the app does not serve: {missing}"
