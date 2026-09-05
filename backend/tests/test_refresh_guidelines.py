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


def _router_prefixes() -> dict[str, str]:
    """module name -> the prefix main.py mounts it under."""
    import ast
    import pathlib as _pl

    main = _pl.Path(__file__).resolve().parents[1] / "main.py"
    out: dict[str, str] = {}
    for node in ast.walk(ast.parse(main.read_text())):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "include_router" or not node.args:
            continue
        target = node.args[0]
        # `pipeline.router` or a bare `guidelines_router`
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            name = target.value.id
        elif isinstance(target, ast.Name):
            name = target.id
        else:
            continue
        prefix = ""
        for kw in node.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                prefix = str(kw.value.value)
        out[name] = prefix
    return out


def _declared_paths(module: str, method: str) -> set[str]:
    """The paths a router module declares for one HTTP method, un-prefixed."""
    import ast
    import pathlib as _pl

    source = _pl.Path(__file__).resolve().parents[1] / "routers" / f"{module}.py"
    found: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text())):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call) or not isinstance(deco.func, ast.Attribute):
                continue
            if deco.func.attr != method.lower() or not deco.args:
                continue
            if isinstance(deco.args[0], ast.Constant):
                found.add(str(deco.args[0].value))
    return found


def test_the_trigger_paths_include_the_router_prefix() -> None:
    """The bug this exists for: a URL built from the decorator alone.

    `@router.post("/diseases/{slug}/guideline-synthesis/run")` is not the URL — the
    prefix is applied at include_router, and for the pipeline router that prefix is
    /api/pipeline. Posting to the un-prefixed path returned 405 rather than 404,
    because the SPA catch-all answers it, so the failure read like a broken endpoint
    instead of a wrong address.

    Read from the source rather than from a built app: this has to hold regardless of
    what an imported app object looks like under a given environment or test order.
    """
    prefix = _router_prefixes().get("pipeline")
    assert prefix == "/api/pipeline", f"pipeline router prefix moved to {prefix!r}"

    declared = _declared_paths("pipeline", "POST")
    for flow in ("guideline-synthesis", "guideline-shelf"):
        want = rg._TRIGGER_PATH.replace("{flow}", flow)
        tail = "/diseases/{slug}/" + flow + "/run"
        assert tail in declared, f"the pipeline router no longer declares {tail}"
        assert want == prefix + tail, f"script calls {want}, the app serves {prefix + tail}"


def test_the_status_path_includes_the_agent_router_prefix() -> None:
    prefix = _router_prefixes().get("agent")
    assert prefix == "/api/agent", f"agent router prefix moved to {prefix!r}"

    tail = "/run/{execution_id}"
    assert tail in _declared_paths("agent", "GET")
    assert rg._STATUS_PATH == prefix + tail
