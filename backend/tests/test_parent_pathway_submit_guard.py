"""Tests for pp-synth draft guard after agentic synthesis."""
from __future__ import annotations

import backend.content_db as content_db
from backend.flows.parent_pathway.submit_guard import parent_pathway_synth_missing_draft_error


def test_guard_ignored_for_other_nodes() -> None:
    assert (
        parent_pathway_synth_missing_draft_error(
            "parent_pathway",
            "pp-plan",
            {"disease_initial": {"disease_slug": "noonan"}},
        )
        is None
    )


def test_guard_requires_draft_for_pp_synth(monkeypatch) -> None:
    monkeypatch.setattr(content_db, "get_parent_pathway_draft", lambda _slug: None)
    err = parent_pathway_synth_missing_draft_error(
        "parent_pathway",
        "pp-synth",
        {"disease_initial": {"disease_slug": "noonan"}},
    )
    assert err is not None
    assert "submit_parent_pathway" in err


def test_guard_passes_when_draft_exists(monkeypatch) -> None:
    monkeypatch.setattr(
        content_db,
        "get_parent_pathway_draft",
        lambda _slug: {"tree": {"id": "root"}},
    )
    assert (
        parent_pathway_synth_missing_draft_error(
            "parent_pathway",
            "pp-synth",
            {"disease_initial": {"disease_slug": "noonan"}},
        )
        is None
    )
