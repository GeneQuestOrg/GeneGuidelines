"""Integration tests for the post-run publish bridge.

Exercises the hook called from :func:`backend.routers.agent.execute_agent_async`
in its ``finally`` block: a successful PubMed run with a ``disease_slug`` must
land an ``ai-draft`` row in ``guideline_documents`` so the public reader can
serve ``GET /api/diseases/<slug>/guideline/document`` for a freshly bootstrapped
disease.

The hook itself is synchronous; we call it directly to skip the full agent
run-loop and prove the bridge in isolation. The DB shape and seed lifecycle are
the real assertions.
"""

from __future__ import annotations

import json

import pytest

from backend.content_db import get_guideline_document
from backend.database import get_connection, init_db
from backend.routers.agent import _post_run_publish_guideline_document


_TEST_SLUG = "publish-bridge-test-disease"


@pytest.fixture
def disease_row():
    """Seed a synthetic disease row so the guideline_documents FK is satisfied."""
    init_db()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM guideline_documents WHERE disease_slug = %s", (_TEST_SLUG,))
    cur.execute("DELETE FROM diseases WHERE slug = %s", (_TEST_SLUG,))
    cur.execute(
        """
        INSERT INTO diseases (
            slug, name, name_short, omim, gene, inheritance, summary,
            types_json, related_json, prevalence_text, status, status_by,
            status_date, ai_draft_date, open_prs, doctors_count, trials_count,
            coverage, accent, guideline_prompt_profile_json
        ) VALUES (%s, %s, %s, '', '', '', '', '[]', '[]', 'Rare disease',
                  'ai-draft', NULL, NULL, NULL, 0, 0, 0, 'skeleton', 'indigo', '{}')
        """,
        (_TEST_SLUG, "Publish Bridge Test Disease", "Test"),
    )
    conn.commit()
    conn.close()
    yield _TEST_SLUG
    # Cleanup so reruns of the suite stay isolated.
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM guideline_documents WHERE disease_slug = %s", (_TEST_SLUG,))
    cur.execute("DELETE FROM diseases WHERE slug = %s", (_TEST_SLUG,))
    conn.commit()
    conn.close()


def _pubmed_store(*, slug: str, exec_id: str, error: str | None = None) -> dict:
    output = {
        "disease_name": "Publish Bridge Test Disease",
        "guideline_html": "<p>Top-level draft.</p>",
        "diagnostic_algorithm_html": "<p>Sequence the gene (PMID: 23456789).</p>",
        "treatment_steps_html": "<p>Symptomatic management.</p>",
        "monitoring_protocol_html": "",
        "red_flags_html": "<p>Watch for X.</p>",
        "follow_up_schedule_html": "",
        "evidence_gaps_html": "",
        "article_count": 42,
        "evidence_score": 60,
    }
    return {
        "execution_id": exec_id,
        "flow_key": "pubmed",
        "disease_slug": slug,
        "label": "Publish Bridge Test Disease",
        "output": json.dumps(output),
        "error": error,
        "done": True,
    }


def test_successful_pubmed_run_lands_in_guideline_documents(disease_row) -> None:
    slug = disease_row
    assert get_guideline_document(slug) is None  # baseline

    _post_run_publish_guideline_document(
        "exec-publish-bridge-001",
        _pubmed_store(slug=slug, exec_id="exec-publish-bridge-001"),
    )

    doc = get_guideline_document(slug)
    assert doc is not None
    assert doc["slug"] == slug
    assert doc["version"] == "ai-draft-exec-pub"
    assert doc["status"] == "ai-draft"
    section_ids = [s["id"] for s in doc["sections"]]
    assert "diagnostics" in section_ids
    assert "red-flags" in section_ids
    assert "treatment" in section_ids


def test_run_with_error_does_not_publish(disease_row) -> None:
    slug = disease_row
    _post_run_publish_guideline_document(
        "exec-publish-bridge-err",
        _pubmed_store(slug=slug, exec_id="exec-publish-bridge-err", error="timeout"),
    )
    assert get_guideline_document(slug) is None


def test_idempotent_rerun_overwrites_version(disease_row) -> None:
    slug = disease_row
    _post_run_publish_guideline_document(
        "exec-publish-bridge-first",
        _pubmed_store(slug=slug, exec_id="exec-publish-bridge-first"),
    )
    first = get_guideline_document(slug)
    assert first is not None and first["version"] == "ai-draft-exec-pub"

    _post_run_publish_guideline_document(
        "exec-second-12345678",
        _pubmed_store(slug=slug, exec_id="exec-second-12345678"),
    )
    second = get_guideline_document(slug)
    assert second is not None
    assert second["version"] == "ai-draft-exec-sec"
    # Single row per disease — the first was overwritten, not appended.
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS c FROM guideline_documents WHERE disease_slug = %s",
        (slug,),
    )
    count = cur.fetchone()["c"]
    conn.close()
    assert count == 1


def test_non_pubmed_flow_is_skipped(disease_row) -> None:
    slug = disease_row
    store = _pubmed_store(slug=slug, exec_id="exec-other-flow")
    store["flow_key"] = "doctor_finder"
    _post_run_publish_guideline_document("exec-other-flow", store)
    assert get_guideline_document(slug) is None


def test_missing_output_is_skipped(disease_row) -> None:
    slug = disease_row
    store = _pubmed_store(slug=slug, exec_id="exec-empty-output")
    store["output"] = ""
    _post_run_publish_guideline_document("exec-empty-output", store)
    assert get_guideline_document(slug) is None
