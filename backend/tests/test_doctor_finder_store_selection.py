"""Catalog run-selection policy for doctor_finder snapshots.

Pins the rule that a precision re-run (smaller, more accurate) REPLACES an older,
larger run, while a near-empty transient failure never shadows a real run.
"""
from __future__ import annotations

import json

from backend.doctor_finder_store import _select_best_catalog_runs


def _row(eid: str, slug: str, n_authors: int, started: str, *, name: str = "X"):
    report = {"top_authors": [{"rank": i} for i in range(n_authors)]}
    return {
        "execution_id": eid,
        "disease_name": name,
        "catalog_slug": slug,
        "doctor_report_json": json.dumps(report),
        "started_at": started,
    }


def _no_slug(_name: str):
    return None


def test_recent_smaller_precise_run_replaces_old_large_run():
    # The centrality-gate case: a newer, smaller run must win over the bloated old one.
    rows = [
        _row("new", "fd", 700, "2026-06-25T09:00:00"),
        _row("old", "fd", 1005, "2026-06-20T00:00:00"),
    ]
    best = _select_best_catalog_runs(rows, slug_resolver=_no_slug)
    assert best["fd"][0] == "new"


def test_empty_blip_does_not_shadow_real_run():
    rows = [
        _row("blip", "fd", 1, "2026-06-25T10:00:00"),
        _row("real", "fd", 800, "2026-06-24T00:00:00"),
    ]
    best = _select_best_catalog_runs(rows, slug_resolver=_no_slug)
    assert best["fd"][0] == "real"


def test_all_below_floor_keeps_largest():
    rows = [
        _row("a", "fd", 1, "2026-06-25T10:00:00"),
        _row("b", "fd", 2, "2026-06-24T00:00:00"),
    ]
    best = _select_best_catalog_runs(rows, slug_resolver=_no_slug)
    assert best["fd"][0] == "b"  # 2 authors > 1 author


def test_slug_resolved_from_disease_name_when_catalog_slug_missing():
    rows = [_row("x", "", 50, "2026-06-25T00:00:00", name="Fibrous dysplasia")]
    best = _select_best_catalog_runs(
        rows, slug_resolver=lambda n: "fd" if "ibrous" in n else None
    )
    assert best.get("fd", (None,))[0] == "x"


def test_independent_slugs_each_get_their_own_choice():
    rows = [
        _row("fd-new", "fd", 600, "2026-06-25T09:00:00"),
        _row("fd-old", "fd", 900, "2026-06-20T00:00:00"),
        _row("mas-only", "mas", 120, "2026-06-25T08:00:00"),
    ]
    best = _select_best_catalog_runs(rows, slug_resolver=_no_slug)
    assert best["fd"][0] == "fd-new"
    assert best["mas"][0] == "mas-only"
