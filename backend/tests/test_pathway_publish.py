"""Draft vs publish workflow for parent care pathways.

Tests must not write pathway drafts for real catalog slugs like ``fd`` — they share
the same SQLite file as local ``uvicorn`` (``backend/tickets.db``), which would
overwrite operator drafts and make the admin preview look like "no real result".
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.content_db import (
    ensure_care_pathway_draft_columns,
    get_parent_pathway,
    get_parent_pathway_draft,
    publish_parent_pathway,
    save_parent_pathway,
)
from backend.tests.parent_pathway_fixtures import ABOUT_SUMMARY_MIN, three_action_steps


def _insert_isolated_pathway_catalog_disease(slug: str) -> None:
    """Minimal diseases row so save_parent_pathway / publish API can run."""
    from backend.database import get_connection

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM diseases WHERE slug = %s", (slug,))
    if cur.fetchone():
        conn.close()
        return
    cur.execute(
        """
        INSERT INTO diseases (
            slug, name, name_short, omim, gene, inheritance, summary,
            types_json, related_json, prevalence_text, status, status_by,
            status_date, ai_draft_date, open_prs, doctors_count, trials_count,
            coverage, accent, guideline_prompt_profile_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            slug,
            "Pathway publish test disease",
            "PPT",
            "0",
            "TEST",
            "n/a",
            "Synthetic catalog row for pathway publish tests only.",
            "[]",
            "[]",
            "n/a",
            "pending",
            None,
            None,
            None,
            0,
            0,
            0,
            "skeleton",
            "slate",
            "{}",
        ),
    )
    conn.commit()
    conn.close()


def _delete_isolated_pathway_catalog_disease(slug: str) -> None:
    from backend.database import get_connection

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM care_pathways WHERE disease_slug = %s", (slug,))
    cur.execute("DELETE FROM diseases WHERE slug = %s", (slug,))
    conn.commit()
    conn.close()


@pytest.fixture
def pathway_publish_slug() -> str:
    slug = f"pathway-test-{uuid.uuid4().hex[:10]}"
    _insert_isolated_pathway_catalog_disease(slug)
    try:
        yield slug
    finally:
        _delete_isolated_pathway_catalog_disease(slug)


def _minimal_tree(*, title: str = "Test pathway") -> dict:
    return {
        "id": "root",
        "title": title,
        "subtitle": "Short subtitle for families after diagnosis — one week at a time.",
        "about": {
            "title": "What is this condition?",
            "summary": ABOUT_SUMMARY_MIN,
        },
        "children": three_action_steps(),
    }


# AUTH-2: POST /api/pipeline/pathway-publish now requires superadmin. Authorise
# via the legacy API-key fallback and override account deps with in-memory fakes
# so the guard resolves without constructing the production SQLAlchemy user repo.
_API_KEY = "pathway-publish-test-key"
_ADMIN_HEADERS = {"Authorization": f"Bearer {_API_KEY}"}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    from backend.account.deps import (
        provide_account_service,
        provide_user_repo,
        provide_verifier,
    )
    from backend.account.jwt import Auth0Verifier
    from backend.account.repository import InMemoryUserRepo
    from backend.account.service import AccountService
    from backend.content_db import ensure_content_schema, seed_content_if_empty
    from backend.database import init_db
    from backend.main import app

    init_db()
    ensure_content_schema()
    ensure_care_pathway_draft_columns()
    seed_content_if_empty()

    monkeypatch.setenv("GENEGUIDELINES_API_KEY", _API_KEY)
    repo = InMemoryUserRepo()
    service = AccountService(repo=repo, superadmin_emails=frozenset())
    app.dependency_overrides[provide_verifier] = lambda: Auth0Verifier(domain="", audience="")
    app.dependency_overrides[provide_user_repo] = lambda: repo
    app.dependency_overrides[provide_account_service] = lambda: service
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(provide_verifier, None)
        app.dependency_overrides.pop(provide_user_repo, None)
        app.dependency_overrides.pop(provide_account_service, None)


def test_save_draft_then_publish(pathway_publish_slug: str) -> None:
    ensure_care_pathway_draft_columns()
    slug = pathway_publish_slug
    tree = _minimal_tree(title="Draft pathway for publish test")

    save_parent_pathway(
        slug,
        tree,
        version="v-test-draft",
        based_on="test",
        locale="en",
    )
    draft = get_parent_pathway_draft(slug)
    assert draft is not None
    assert draft["tree"]["title"] == "Draft pathway for publish test"

    published_before = get_parent_pathway(slug)
    old_title = (published_before or {}).get("tree", {}).get("title")

    published = publish_parent_pathway(slug)
    assert published["tree"]["title"] == "Draft pathway for publish test"
    assert published["tree"]["about"]["title"] == "What is this condition?"

    public = get_parent_pathway(slug)
    assert public is not None
    assert public["tree"]["title"] == "Draft pathway for publish test"
    assert public["tree"]["title"] != old_title or old_title in (
        None,
        "Draft pathway for publish test",
    )


def test_pathway_publish_api(client: TestClient, pathway_publish_slug: str) -> None:
    slug = pathway_publish_slug
    tree = _minimal_tree(title="API publish pathway test")
    save_parent_pathway(slug, tree, version="v-api-draft", based_on="test", locale="en")

    resp = client.post(
        "/api/pipeline/pathway-publish",
        json={"disease_slug": slug},
        headers=_ADMIN_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["diseaseSlug"] == slug
    assert body["tree"]["title"] == "API publish pathway test"
    assert body["tree"]["about"]["summary"]

    public = client.get(f"/api/diseases/{slug}/pathway")
    assert public.status_code == 200
    assert public.json()["tree"]["title"] == "API publish pathway test"


def test_publish_without_draft_raises() -> None:
    with pytest.raises(ValueError, match="No draft"):
        publish_parent_pathway("unknown-slug-xyz-pathway")


def test_seed_has_about_section() -> None:
    path = Path(__file__).resolve().parents[1] / "content_care_pathway_seed.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "about" in data["fd"]
    assert data["fd"]["about"]["summary"]
