"""Bootstrap catalog metadata upsert — summary/inheritance survive repeat runs."""

from __future__ import annotations

import pytest

from backend.content_db import get_disease_by_slug, update_disease_catalog_from_bootstrap
from backend.database import get_connection, init_db

_TEST_SLUG = "bootstrap-catalog-upsert-test"


@pytest.fixture
def disease_row():
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
        ) VALUES (%s, %s, %s, '', 'SMN1', '', '', '[]', '[]', 'Rare disease',
                  'ai-draft', NULL, NULL, NULL, 0, 0, 0, 'skeleton', 'indigo', '{}')
        """,
        (_TEST_SLUG, "Spinal Muscular Atrophy", "SMA"),
    )
    conn.commit()
    conn.close()
    yield _TEST_SLUG
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM diseases WHERE slug = %s", (_TEST_SLUG,))
    conn.commit()
    conn.close()


def test_update_disease_catalog_from_bootstrap_fills_empty_fields(disease_row: str) -> None:
    slug = disease_row
    update_disease_catalog_from_bootstrap(
        slug,
        inheritance="Autosomal recessive",
        summary="Motor neuron disease caused by SMN1 loss; severity correlates with SMN2 copy number.",
        types=["Type 1", "Type 2", "Type 3", "Type 4"],
    )
    row = get_disease_by_slug(slug)
    assert row is not None
    assert row["inheritance"] == "Autosomal recessive"
    assert "SMN1" in row["summary"]
    assert row["types"] == ["Type 1", "Type 2", "Type 3", "Type 4"]
