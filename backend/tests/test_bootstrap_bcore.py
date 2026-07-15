"""B-core regression tests — the seams that were untested and let the FOP gaps ship.

Covers:
  * B7a/B7b — finalize_bootstrapped_disease flips coverage skeleton->full and
    stamps the completion marker (previously NO code ever set 'full').
  * B2a — bootstrap_disease_research fans out the shelf builder (previously it
    only ran the finders + legacy 'pubmed' guideline, so a fresh disease got 0
    bibliography rows).
"""

from __future__ import annotations

import asyncio

import pytest

from backend import content_db
from backend.content_db import (
    finalize_bootstrapped_disease,
    get_disease_by_slug,
    set_disease_coverage,
)
from backend.database import get_connection, init_db

_TEST_SLUG = "bcore-finalize-test"


@pytest.fixture
def skeleton_disease():
    init_db()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM diseases WHERE slug = %s", (_TEST_SLUG,))
    cur.execute(
        """
        INSERT INTO diseases (
            slug, name, name_short, omim, gene, inheritance, summary,
            types_json, related_json, prevalence_text, status, status_by,
            status_date, ai_draft_date, open_prs, doctors_count, trials_count,
            coverage, accent, guideline_prompt_profile_json
        ) VALUES (%s, %s, %s, '', 'PHEX', '', '', '[]', '[]', 'Rare disease',
                  'ai-draft', NULL, NULL, NULL, 0, 0, 0, 'skeleton', 'indigo', '{}')
        """,
        (_TEST_SLUG, "B-core Finalize Test", "BCFT"),
    )
    conn.commit()
    conn.close()
    yield _TEST_SLUG
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM diseases WHERE slug = %s", (_TEST_SLUG,))
    conn.commit()
    conn.close()


def test_set_disease_coverage_flips_and_rejects_unknown(skeleton_disease: str) -> None:
    slug = skeleton_disease
    assert get_disease_by_slug(slug)["coverage"] == "skeleton"
    set_disease_coverage(slug, "full")
    assert get_disease_by_slug(slug)["coverage"] == "full"
    # defensive: an unknown value is ignored, not written
    set_disease_coverage(slug, "bogus")
    assert get_disease_by_slug(slug)["coverage"] == "full"


def test_finalize_bootstrapped_disease_reconciles_row(skeleton_disease: str) -> None:
    slug = skeleton_disease
    result = finalize_bootstrapped_disease(slug)
    assert result["finalized"] is True
    assert result["coverage"] == "full"
    row = get_disease_by_slug(slug)
    assert row["coverage"] == "full"  # B7a
    assert row["aiDraftDate"], "completion marker (ai_draft_date) must be stamped"  # B7b
    # doctors_count is refreshed via the previously-dead refresh_disease_doctors_count
    assert isinstance(result["doctors_count"], int)


def test_finalize_unknown_slug_is_noop() -> None:
    result = finalize_bootstrapped_disease("no-such-disease-xyz")
    assert result["finalized"] is False


def test_bootstrap_fanout_includes_shelf(monkeypatch: pytest.MonkeyPatch) -> None:
    """B2a guard: the fan-out must fire the shelf builder, not only finders+guideline.

    All child launchers are stubbed so no PubMed/LLM/DB work runs — we only assert
    the orchestration wires up (and returns) the shelf workflow.
    """
    from backend.services import disease_bootstrap as db_boot

    async def _noop_finder(**_kw):
        return None

    for mod_name, fn in [
        ("official_guidelines_finder", "find_official_guideline_for_disease"),
        ("trials_finder", "find_trials_for_disease"),
        ("therapies_finder", "find_therapies_for_disease"),
        ("foundations_finder", "find_foundations_for_disease"),
    ]:
        mod = __import__(f"backend.services.{mod_name}", fromlist=[fn])
        monkeypatch.setattr(mod, fn, _noop_finder)

    started: list[str] = []

    async def _fake_doctor(*_a, **_k):
        started.append("doctor")
        return "df-x"

    async def _fake_guideline(*_a, **_k):
        started.append("guideline")
        return "gl-x"

    async def _fake_shelf(*_a, **_k):
        started.append("shelf")
        return "shelf-x"

    monkeypatch.setattr(db_boot, "_start_doctor_finder", _fake_doctor)
    monkeypatch.setattr(db_boot, "_start_guideline_run", _fake_guideline)
    monkeypatch.setattr(db_boot, "_start_shelf_build", _fake_shelf)

    result = asyncio.run(
        db_boot.bootstrap_disease_research(
            disease_slug="bcore-fanout-test",
            disease_name="B-core Fanout Test",
            profile="test",
        )
    )
    assert "shelf" in result and result["shelf"] == "shelf-x", "shelf builder must be in the fan-out"
    assert "shelf" in started, "_start_shelf_build must be invoked"
    # sanity: the other core workflows are still wired
    assert set(result) >= {"official_guidelines", "trials", "therapies", "foundations", "doctor_finder", "guideline", "shelf"}
