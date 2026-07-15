"""Postgres access for public diseases and guideline metadata (Phase 4)."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

try:
    from .config import BACKEND_DIR
    from .database import get_connection
    from .db import table_columns, table_exists
    from .guideline_prompt_profile import (
        empty_guideline_prompt_profile,
        normalize_guideline_prompt_profile,
    )
except ImportError:
    from config import BACKEND_DIR
    from database import get_connection
    from db import table_columns, table_exists
    from guideline_prompt_profile import (
        empty_guideline_prompt_profile,
        normalize_guideline_prompt_profile,
    )

CONTENT_SEED_PATH = BACKEND_DIR / "content_seed.json"
GUIDELINE_BODIES_PATH = BACKEND_DIR / "content_guideline_documents.json"
CARE_PATHWAY_SEED_PATH = BACKEND_DIR / "content_care_pathway_seed.json"
PR_PARA_MAPS_PATH = BACKEND_DIR / "content_pr_para_maps.json"
TRIALS_SEED_PATH = BACKEND_DIR / "content_trials_seed.json"
THERAPIES_SEED_PATH = BACKEND_DIR / "content_therapies_seed.json"
FOUNDATIONS_SEED_PATH = BACKEND_DIR / "content_foundations_seed.json"
OFFICIAL_GUIDELINES_SEED_PATH = BACKEND_DIR / "content_official_guidelines_seed.json"
DISEASE_SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")
MAX_DISEASE_SLUG_LEN = 64
PR_ID_PATTERN = re.compile(r"^PR-[0-9]+$")
MAX_PR_ID_LEN = 32
PR_STATUSES = frozenset({"pending", "under-review", "verified", "rejected"})


def normalize_disease_slug(slug: str) -> str | None:
    """Return normalized slug or None if invalid (path traversal safe)."""
    trimmed = slug.strip().lower()
    if not trimmed or len(trimmed) > MAX_DISEASE_SLUG_LEN:
        return None
    if not DISEASE_SLUG_PATTERN.match(trimmed):
        return None
    return trimmed


def ensure_content_schema() -> None:
    """Create diseases / guideline_documents tables if missing."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS diseases (
            slug TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            name_short TEXT NOT NULL,
            omim TEXT NOT NULL,
            gene TEXT NOT NULL,
            inheritance TEXT NOT NULL,
            summary TEXT NOT NULL,
            types_json TEXT NOT NULL DEFAULT '[]',
            related_json TEXT NOT NULL DEFAULT '[]',
            prevalence_text TEXT NOT NULL,
            status TEXT NOT NULL,
            status_by TEXT,
            status_date TEXT,
            ai_draft_date TEXT,
            open_prs INTEGER NOT NULL DEFAULT 0,
            doctors_count INTEGER NOT NULL DEFAULT 0,
            trials_count INTEGER NOT NULL DEFAULT 0,
            coverage TEXT NOT NULL,
            accent TEXT NOT NULL,
            guideline_prompt_profile_json TEXT NOT NULL DEFAULT '{}',
            listed INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS guideline_documents (
            disease_slug TEXT PRIMARY KEY REFERENCES diseases(slug) ON DELETE CASCADE,
            version TEXT NOT NULL,
            locale TEXT NOT NULL DEFAULT 'en',
            section_count INTEGER NOT NULL DEFAULT 0,
            last_reviewed TEXT,
            sections_json TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_stats (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            disease_count INTEGER NOT NULL,
            doctor_count INTEGER NOT NULL,
            recruiting_trial_count INTEGER NOT NULL,
            open_pr_count INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS content_prs (
            id TEXT PRIMARY KEY,
            disease_slug TEXT NOT NULL REFERENCES diseases(slug),
            title TEXT NOT NULL,
            opened TEXT NOT NULL,
            status TEXT NOT NULL,
            author TEXT NOT NULL DEFAULT 'AI Watcher',
            reviewer TEXT,
            summary TEXT NOT NULL,
            citations_count INTEGER NOT NULL DEFAULT 0,
            diff_json TEXT NOT NULL DEFAULT '[]',
            papers_json TEXT NOT NULL DEFAULT '[]'
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS care_pathways (
            disease_slug TEXT NOT NULL REFERENCES diseases(slug) ON DELETE CASCADE,
            kind TEXT NOT NULL DEFAULT 'diagnosis'
                CHECK (kind IN ('diagnosis','monitoring','post_treatment')),
            locale TEXT NOT NULL DEFAULT 'en',
            version TEXT NOT NULL,
            based_on TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            source_guideline_version TEXT,
            source_execution_id TEXT,
            tree_json TEXT NOT NULL,
            PRIMARY KEY (disease_slug, kind)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trials (
            nct TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            phase TEXT NOT NULL,
            status TEXT NOT NULL,
            sponsor TEXT NOT NULL,
            city TEXT,
            country TEXT,
            lat REAL,
            lng REAL,
            age_range TEXT,
            principal_investigator TEXT,
            eligibility_summary TEXT NOT NULL DEFAULT '',
            enrollment_target INTEGER,
            enrolled INTEGER,
            contact TEXT,
            last_seen TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS disease_trials (
            disease_slug TEXT NOT NULL REFERENCES diseases(slug) ON DELETE CASCADE,
            nct TEXT NOT NULL REFERENCES trials(nct) ON DELETE CASCADE,
            PRIMARY KEY (disease_slug, nct)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS therapies (
            id SERIAL PRIMARY KEY,
            disease_slug TEXT NOT NULL REFERENCES diseases(slug) ON DELETE CASCADE,
            name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('consensus','verified','pending','preclinical')),
            note TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 100
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS foundations (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            scope TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            city TEXT,
            country TEXT,
            services_json TEXT NOT NULL DEFAULT '[]',
            source TEXT NOT NULL DEFAULT 'seed'
                CHECK (source IN ('seed','workflow','reviewer'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS disease_foundations (
            disease_slug TEXT NOT NULL REFERENCES diseases(slug) ON DELETE CASCADE,
            foundation_id INTEGER NOT NULL REFERENCES foundations(id) ON DELETE CASCADE,
            PRIMARY KEY (disease_slug, foundation_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS private_contexts (
            id SERIAL PRIMARY KEY,
            disease_slug TEXT NOT NULL REFERENCES diseases(slug) ON DELETE CASCADE,
            original_filename TEXT NOT NULL,
            original_chars INTEGER NOT NULL DEFAULT 0,
            original_sha256 TEXT NOT NULL DEFAULT '',
            uploaded_at TEXT NOT NULL,
            redacted_json TEXT NOT NULL DEFAULT '{}',
            pii_tokens_removed INTEGER NOT NULL DEFAULT 0,
            clinical_facts_extracted INTEGER NOT NULL DEFAULT 0,
            model_used TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','ready','failed')),
            error TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    ensure_guideline_prompt_column()
    ensure_listed_column()
    ensure_care_pathway_draft_columns()
    ensure_official_guideline_pointers_schema()
    ensure_foundations_source_column()
    sync_guideline_document_bodies_from_file()
    # NOTE: content_prs and disease_trials have FKs to diseases(slug); their
    # seeders (seed_content_prs_if_empty / seed_trials_from_file) are invoked
    # from database.init_db() AFTER seed_content_if_empty() so the parent
    # rows exist. Keeping those calls here would fire them on an empty
    # diseases table and skip the junction inserts silently.
    seed_care_pathways_from_file()


def ensure_care_pathway_draft_columns() -> None:
    """Add draft_tree_json + kind for existing deployments.

    SQLite cannot ALTER PRIMARY KEY in place, so the kind column lives next
    to the existing single-row-per-disease layout. New code keys lookups on
    (disease_slug, kind) — old rows surface as kind='diagnosis' which is
    the documented default.
    """
    conn = get_connection()
    cur = conn.cursor()
    columns = table_columns(conn, "care_pathways")
    if "draft_tree_json" not in columns:
        cur.execute("ALTER TABLE care_pathways ADD COLUMN draft_tree_json TEXT")
    if "draft_updated_at" not in columns:
        cur.execute("ALTER TABLE care_pathways ADD COLUMN draft_updated_at TEXT")
    if "kind" not in columns:
        cur.execute(
            "ALTER TABLE care_pathways ADD COLUMN kind TEXT NOT NULL DEFAULT 'diagnosis'"
        )
    conn.commit()
    conn.close()


def ensure_official_guideline_pointers_schema() -> None:
    """Create the official_guideline_pointers table if missing."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS official_guideline_pointers (
            disease_slug TEXT PRIMARY KEY REFERENCES diseases(slug) ON DELETE CASCADE,
            title TEXT NOT NULL,
            authors TEXT NOT NULL,
            year INTEGER NOT NULL,
            journal TEXT NOT NULL,
            pmid TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            confirmed_by TEXT NOT NULL DEFAULT '',
            confirmed_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'reviewer'
                CHECK (source IN ('reviewer','workflow','seed'))
        )
        """
    )
    conn.commit()
    conn.close()


def ensure_foundations_source_column() -> None:
    """Add foundations.source for existing deployments (foundations-as-workflow).

    Existing rows were all seeded from content_foundations_seed.json, so the
    backfill default of 'seed' is correct: they stay visible until the
    foundations_finder workflow produces 'workflow' rows for a disease, at
    which point the workflow rows take over as the primary source (see
    :meth:`SqlaFoundationRepo.list_for_disease`). Zero regression — every
    current row keeps showing as a seed fallback.
    """
    conn = get_connection()
    cur = conn.cursor()
    columns = table_columns(conn, "foundations")
    if "source" not in columns:
        cur.execute(
            "ALTER TABLE foundations ADD COLUMN source TEXT NOT NULL DEFAULT 'seed'"
        )
        conn.commit()
    conn.close()


def ensure_guideline_prompt_column() -> None:
    """Add guideline_prompt_profile_json to diseases if missing (existing deployments)."""
    conn = get_connection()
    cur = conn.cursor()
    columns = table_columns(conn, "diseases")
    column_added = False
    if "guideline_prompt_profile_json" not in columns:
        cur.execute(
            "ALTER TABLE diseases ADD COLUMN guideline_prompt_profile_json TEXT NOT NULL DEFAULT '{}'"
        )
        conn.commit()
        column_added = True
    conn.close()
    if column_added:
        sync_guideline_prompts_from_seed()


def ensure_listed_column() -> None:
    """Add diseases.listed for existing deployments (RES-1, unlisted-until-approve).

    Existing rows default to 1 (visible — zero regression). New diseases from
    the public bootstrap endpoint are inserted with 0 and stay out of the
    catalog index until a superadmin approves them.
    """
    conn = get_connection()
    cur = conn.cursor()
    columns = table_columns(conn, "diseases")
    if "listed" not in columns:
        cur.execute(
            "ALTER TABLE diseases ADD COLUMN listed INTEGER NOT NULL DEFAULT 1"
        )
        conn.commit()
    conn.close()


def set_disease_listed(slug: str, listed: bool) -> dict[str, Any] | None:
    """Set diseases.listed (RES-1 approve). Returns the updated disease or None.

    Resource-style mutation behind the content domain's PATCH endpoint. The
    semantics of ``status`` (epistemic state) are intentionally left untouched.
    """
    normalized = normalize_disease_slug(slug)
    if normalized is None:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM diseases WHERE slug = %s", (normalized,))
    if cur.fetchone() is None:
        conn.close()
        return None
    cur.execute(
        "UPDATE diseases SET listed = %s WHERE slug = %s",
        (1 if listed else 0, normalized),
    )
    conn.commit()
    cur.execute("SELECT * FROM diseases WHERE slug = %s", (normalized,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_disease(row)


def list_unlisted_diseases() -> list[dict[str, Any]]:
    """Diseases pending catalog approval (listed=0), newest research first.

    Backs the admin "Catalog" review queue. Returns the full disease dicts so
    the admin table can show slug / name / status / created markers.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM diseases WHERE listed = 0 ORDER BY lower(name)")
    rows = cur.fetchall()
    conn.close()
    return [_row_to_disease(r) for r in rows]


def sync_guideline_prompts_from_seed() -> None:
    """Backfill per-disease prompt profiles from content_seed.json when still empty."""
    path = Path(CONTENT_SEED_PATH)
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    conn = get_connection()
    cur = conn.cursor()
    for disease in data.get("diseases", []):
        slug = disease.get("slug")
        profile = disease.get("guidelinePromptProfile")
        if not slug or not profile:
            continue
        normalized = normalize_guideline_prompt_profile(profile)
        if normalized == empty_guideline_prompt_profile():
            continue
        cur.execute(
            "SELECT guideline_prompt_profile_json FROM diseases WHERE slug = %s",
            (slug,),
        )
        row = cur.fetchone()
        if row is None:
            continue
        existing = normalize_guideline_prompt_profile(
            json.loads(row["guideline_prompt_profile_json"] or "{}")
        )
        if existing != empty_guideline_prompt_profile():
            continue
        cur.execute(
            "UPDATE diseases SET guideline_prompt_profile_json = %s WHERE slug = %s",
            (json.dumps(normalized, ensure_ascii=False), slug),
        )
    conn.commit()
    conn.close()


def seed_content_if_empty() -> None:
    """Load content_seed.json when diseases table has no rows."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM diseases")
    row = cur.fetchone()
    count = int(row["n"]) if row else 0
    if count > 0:
        conn.close()
        return

    path = Path(CONTENT_SEED_PATH)
    if not path.exists():
        conn.close()
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    for disease in data.get("diseases", []):
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
                disease["slug"],
                disease["name"],
                disease["nameShort"],
                disease["omim"],
                disease["gene"],
                disease["inheritance"],
                disease["summary"],
                json.dumps(disease.get("types", [])),
                json.dumps(disease.get("related", [])),
                disease["prevalenceText"],
                disease["status"],
                disease.get("statusBy"),
                disease.get("statusDate"),
                disease.get("aiDraftDate"),
                disease.get("openPRs", 0),
                disease.get("doctorsCount", 0),
                disease.get("trialsCount", 0),
                disease["coverage"],
                disease["accent"],
                json.dumps(
                    normalize_guideline_prompt_profile(
                        disease.get("guidelinePromptProfile")
                    ),
                    ensure_ascii=False,
                ),
            ),
        )

    for doc in data.get("guideline_documents", []):
        cur.execute(
            """
            INSERT INTO guideline_documents (
                disease_slug, version, locale, section_count, last_reviewed
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                doc["diseaseSlug"],
                doc["version"],
                doc.get("locale", "en"),
                doc.get("sectionCount", 0),
                doc.get("lastReviewed"),
            ),
        )

    stats = data.get("catalog_stats", {})
    cur.execute("DELETE FROM catalog_stats")
    cur.execute(
        """
        INSERT INTO catalog_stats (
            id, disease_count, doctor_count, recruiting_trial_count, open_pr_count
        ) VALUES (1, %s, %s, %s, %s)
        """,
        (
            stats.get("diseaseCount", 0),
            stats.get("doctorCount", 0),
            stats.get("recruitingTrialCount", 0),
            stats.get("openPrCount", 0),
        ),
    )
    _insert_content_prs_from_seed(cur, data.get("content_prs", []))
    conn.commit()
    conn.close()


def normalize_pr_id(pr_id: str) -> str | None:
    """Return normalized PR id or None if invalid."""
    trimmed = pr_id.strip().upper()
    if not trimmed or len(trimmed) > MAX_PR_ID_LEN:
        return None
    if not PR_ID_PATTERN.match(trimmed):
        return None
    return trimmed


def _insert_content_prs_from_seed(cur: Any, prs: list[dict[str, Any]]) -> None:
    for pr in prs:
        pr_id = normalize_pr_id(str(pr.get("id", "")))
        slug = normalize_disease_slug(str(pr.get("diseaseSlug", "")))
        status = str(pr.get("status", "pending"))
        if pr_id is None or slug is None or status not in PR_STATUSES:
            continue
        cur.execute(
            """
            INSERT INTO content_prs (
                id, disease_slug, title, opened, status, author, reviewer,
                summary, citations_count, diff_json, papers_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (
                pr_id,
                slug,
                pr["title"],
                pr["opened"],
                status,
                pr.get("author", "AI Watcher"),
                pr.get("reviewer"),
                pr.get("summary", ""),
                int(pr.get("citationsCount", 0)),
                json.dumps(pr.get("diff", []), ensure_ascii=False),
                json.dumps(pr.get("papers", []), ensure_ascii=False),
            ),
        )


def seed_content_prs_if_empty() -> None:
    """Load content_prs from content_seed.json when the table has no rows."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM content_prs")
    row = cur.fetchone()
    count = int(row["n"]) if row else 0
    if count > 0:
        conn.close()
        return

    path = Path(CONTENT_SEED_PATH)
    if not path.exists():
        conn.close()
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    _insert_content_prs_from_seed(cur, data.get("content_prs", []))
    conn.commit()
    conn.close()


def _row_to_pr_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "disease": row["disease_slug"],
        "title": row["title"],
        "opened": row["opened"],
        "status": row["status"],
    }


def _load_pr_paragraph_map(pr_id: str) -> dict[str, Any] | None:
    path = Path(PR_PARA_MAPS_PATH)
    if not path.exists():
        return None
    maps = json.loads(path.read_text(encoding="utf-8"))
    raw = maps.get(pr_id)
    return raw if isinstance(raw, dict) else None


def _row_to_pr_detail(row: dict[str, Any]) -> dict[str, Any]:
    summary = _row_to_pr_summary(row)
    paragraph_map = _load_pr_paragraph_map(row["id"])
    return {
        **summary,
        "author": row["author"],
        "reviewer": row["reviewer"],
        "summary": row["summary"],
        "citationsCount": int(row["citations_count"]),
        "diff": json.loads(row["diff_json"] or "[]"),
        "papers": json.loads(row["papers_json"] or "[]"),
        "paragraphMap": paragraph_map,
    }


def list_content_prs(
    *,
    status: str | None = None,
    disease_slug: str | None = None,
) -> list[dict[str, Any]]:
    """List guideline PRs, newest opened date first."""
    conn = get_connection()
    cur = conn.cursor()
    clauses: list[str] = []
    params: list[Any] = []
    if status is not None and status in PR_STATUSES:
        clauses.append("status = %s")
        params.append(status)
    if disease_slug is not None:
        normalized = normalize_disease_slug(disease_slug)
        if normalized is not None:
            clauses.append("disease_slug = %s")
            params.append(normalized)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    cur.execute(
        f"""
        SELECT id, disease_slug, title, opened, status
        FROM content_prs
        {where}
        ORDER BY opened DESC, id DESC
        """,
        params,
    )
    rows = cur.fetchall()
    conn.close()
    return [_row_to_pr_summary(r) for r in rows]


def get_content_pr_by_id(pr_id: str) -> dict[str, Any] | None:
    normalized = normalize_pr_id(pr_id)
    if normalized is None:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM content_prs WHERE id = %s", (normalized,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_pr_detail(row)


def _reviewer_name(reviewer: str | None, existing: str | None) -> str:
    value = (reviewer or existing or "GeneGuidelines Operator").strip()
    return value or "GeneGuidelines Operator"


def publish_content_pr(
    pr_id: str,
    *,
    reviewer: str | None = None,
) -> dict[str, Any] | None:
    """Merge PR into guideline document and mark verified. Returns detail or None."""
    normalized = normalize_pr_id(pr_id)
    if normalized is None:
        return None
    if not str(reviewer or "").strip():
        raise GuidelinePrPublishError(
            "reviewer is required to publish a guideline PR — provide operator name or email."
        )

    try:
        from .guideline_pr_publish import GuidelinePrPublishError, publish_pr_to_stored_document
    except ImportError:
        from guideline_pr_publish import GuidelinePrPublishError, publish_pr_to_stored_document

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT disease_slug, reviewer, status FROM content_prs WHERE id = %s",
        (normalized,),
    )
    pr_row = cur.fetchone()
    if pr_row is None:
        conn.close()
        return None

    reviewer_value = _reviewer_name(reviewer, pr_row["reviewer"])
    disease_slug = pr_row["disease_slug"]

    cur.execute(
        "SELECT sections_json FROM guideline_documents WHERE disease_slug = %s",
        (disease_slug,),
    )
    doc_row = cur.fetchone()
    if doc_row is None or not doc_row["sections_json"]:
        conn.close()
        raise GuidelinePrPublishError(
            f"No guideline document body for disease '{disease_slug}'. "
            "Run init_db or sync content_guideline_documents.json."
        )

    document = json.loads(doc_row["sections_json"])
    try:
        updated_doc = publish_pr_to_stored_document(
            document,
            pr_id=normalized,
            reviewer=reviewer_value,
        )
    except GuidelinePrPublishError:
        conn.close()
        raise

    cur.execute(
        """
        UPDATE guideline_documents
        SET sections_json = %s, last_reviewed = %s
        WHERE disease_slug = %s
        """,
        (json.dumps(updated_doc, ensure_ascii=False), _today_iso_for_pr(), disease_slug),
    )
    cur.execute(
        """
        UPDATE content_prs
        SET status = 'verified', reviewer = %s
        WHERE id = %s
        """,
        (reviewer_value, normalized),
    )
    conn.commit()
    cur.execute("SELECT * FROM content_prs WHERE id = %s", (normalized,))
    updated = cur.fetchone()
    conn.close()
    if updated is None:
        return None
    return _row_to_pr_detail(updated)


def _today_iso_for_pr() -> str:
    from datetime import date

    return date.today().isoformat()


def review_content_pr(
    pr_id: str,
    *,
    action: str,
    reviewer: str | None = None,
) -> dict[str, Any] | None:
    """Publish, reject, or request changes on a guideline PR."""
    normalized = normalize_pr_id(pr_id)
    if normalized is None:
        return None

    if action in ("approve", "publish"):
        return publish_content_pr(pr_id, reviewer=reviewer)

    if action == "reject":
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT reviewer FROM content_prs WHERE id = %s", (normalized,))
        row = cur.fetchone()
        if row is None:
            conn.close()
            return None
        reviewer_value = _reviewer_name(reviewer, row["reviewer"])
        cur.execute(
            """
            UPDATE content_prs
            SET status = 'rejected', reviewer = %s
            WHERE id = %s
            """,
            (reviewer_value, normalized),
        )
        conn.commit()
        cur.execute("SELECT * FROM content_prs WHERE id = %s", (normalized,))
        updated = cur.fetchone()
        conn.close()
        if updated is None:
            return None
        return _row_to_pr_detail(updated)

    if action in ("request_changes", "request-changes"):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT reviewer FROM content_prs WHERE id = %s", (normalized,))
        row = cur.fetchone()
        if row is None:
            conn.close()
            return None
        reviewer_value = _reviewer_name(reviewer, row["reviewer"])
        cur.execute(
            """
            UPDATE content_prs
            SET status = 'under-review', reviewer = %s
            WHERE id = %s
            """,
            (reviewer_value, normalized),
        )
        conn.commit()
        cur.execute("SELECT * FROM content_prs WHERE id = %s", (normalized,))
        updated = cur.fetchone()
        conn.close()
        if updated is None:
            return None
        return _row_to_pr_detail(updated)

    return None


def _row_to_disease(row: dict[str, Any], *, include_prompt_profile: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {
        "slug": row["slug"],
        "name": row["name"],
        "nameShort": row["name_short"],
        "omim": row["omim"],
        "gene": row["gene"],
        "inheritance": row["inheritance"],
        "summary": row["summary"],
        "types": json.loads(row["types_json"] or "[]"),
        "related": json.loads(row["related_json"] or "[]"),
        "prevalenceText": row["prevalence_text"],
        "status": row["status"],
        "statusBy": row["status_by"],
        "statusDate": row["status_date"],
        "aiDraftDate": row["ai_draft_date"],
        "openPRs": row["open_prs"],
        "doctorsCount": row["doctors_count"],
        "trialsCount": row["trials_count"],
        "coverage": row["coverage"],
        "accent": row["accent"],
        "listed": bool(row["listed"]) if "listed" in (row.keys() if hasattr(row, "keys") else ()) else True,
    }
    if include_prompt_profile:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        raw = row["guideline_prompt_profile_json"] if "guideline_prompt_profile_json" in keys else "{}"
        out["guidelinePromptProfile"] = normalize_guideline_prompt_profile(
            json.loads(raw or "{}")
        )
    return out


def update_disease_guideline_prompt_profile(slug: str, profile: dict[str, Any]) -> dict[str, Any] | None:
    """Persist profile; returns updated disease or None if slug missing."""
    normalized = normalize_disease_slug(slug)
    if normalized is None:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM diseases WHERE slug = %s", (normalized,))
    if cur.fetchone() is None:
        conn.close()
        return None
    payload = normalize_guideline_prompt_profile(profile)
    cur.execute(
        "UPDATE diseases SET guideline_prompt_profile_json = %s WHERE slug = %s",
        (json.dumps(payload, ensure_ascii=False), normalized),
    )
    conn.commit()
    cur.execute("SELECT * FROM diseases WHERE slug = %s", (normalized,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_disease(row, include_prompt_profile=True)


def _row_to_disease_list_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slug": row["slug"],
        "name": row["name"],
        "nameShort": row["name_short"],
        "gene": row["gene"],
        "summary": row["summary"],
        "coverage": row["coverage"],
        "accent": row["accent"],
    }


def list_diseases_catalog() -> list[dict[str, Any]]:
    """Lightweight catalog rows (no prompt JSON, fewer columns)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT slug, name, name_short, gene, summary, coverage, accent
        FROM diseases
        WHERE listed = 1
        ORDER BY lower(name)
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [_row_to_disease_list_item(r) for r in rows]


def list_diseases() -> list[dict[str, Any]]:
    """Catalog index — visible (listed=1) diseases only (RES-1).

    The single-disease reader :func:`get_disease_by_slug` deliberately does
    NOT filter, so a freshly bootstrapped (unlisted) disease still resolves
    via direct link for the person who launched the run.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM diseases WHERE listed = 1 ORDER BY lower(name)")
    rows = cur.fetchall()
    conn.close()
    return [_row_to_disease(r, include_prompt_profile=False) for r in rows]


def search_diseases_catalog(query: str) -> list[dict[str, Any]]:
    q = query.strip().lower()
    items = list_diseases_catalog()
    if not q:
        return items
    return [
        d
        for d in items
        if q in d["name"].lower()
        or q in d["nameShort"].lower()
        or q in d["gene"].lower()
        or q in d["summary"].lower()
        or q in d["slug"]
    ]


def search_diseases(query: str) -> list[dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return list_diseases()
    return [
        d
        for d in list_diseases()
        if q in d["name"].lower()
        or q in d["nameShort"].lower()
        or q in d["gene"].lower()
        or q in d["summary"].lower()
        or q in d["slug"]
    ]


def refresh_disease_doctors_count(slug: str) -> int:
    """Sync ``diseases.doctors_count`` from the live public doctor directory.

    Called after doctor_finder persistence so home cards stay correct across
    backend restarts (RAM-only finder runs otherwise show 0 after reload).
    """
    normalized = normalize_disease_slug(slug)
    if normalized is None:
        return 0
    try:
        from .doctor_catalog import effective_public_doctor_count_for_disease

        count = effective_public_doctor_count_for_disease(normalized)
    except Exception:
        return 0
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE diseases SET doctors_count = %s WHERE slug = %s",
        (max(0, int(count)), normalized),
    )
    conn.commit()
    conn.close()
    return max(0, int(count))


def set_disease_coverage(slug: str, coverage: str) -> None:
    """Set the ``coverage`` badge for a disease (e.g. ``skeleton`` -> ``full``).

    The single home for the coverage flip so the guideline-publish bridge (B7a)
    and the bootstrap-completion aggregate (B7b) never duplicate the UPDATE. A
    value outside the known set is ignored (defensive — the column is free-text
    but the UI only understands ``skeleton`` / ``full``).
    """
    normalized = normalize_disease_slug(slug)
    if normalized is None:
        return
    value = (coverage or "").strip().lower()
    if value not in ("skeleton", "full"):
        return
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE diseases SET coverage = %s WHERE slug = %s",
        (value, normalized),
    )
    conn.commit()
    conn.close()


def finalize_bootstrapped_disease(slug: str) -> dict[str, Any]:
    """Reconcile a disease row once its bootstrap research has landed (B7b).

    A single idempotent completion step run at the end of the bootstrap fan-out
    (see :func:`backend.services.disease_bootstrap.bootstrap_disease_research`):

      * flips ``coverage`` to ``full`` (the disease now has a guideline + finders;
        composes with B7a via the shared :func:`set_disease_coverage`),
      * refreshes the denormalized ``doctors_count`` from the live public
        directory via :func:`refresh_disease_doctors_count` (previously dead code),
      * stamps ``ai_draft_date`` as the durable "bootstrap completed" marker
        (reused rather than adding a column — migration-free).

    Returns a small summary dict for logging/tests. Safe to call repeatedly.
    """
    normalized = normalize_disease_slug(slug)
    if normalized is None:
        return {"slug": slug, "finalized": False}
    if get_disease_by_slug(normalized) is None:
        # Well-formed slug but no such disease row — nothing to reconcile.
        return {"slug": normalized, "finalized": False}
    set_disease_coverage(normalized, "full")
    doctors_count = refresh_disease_doctors_count(normalized)
    completed_at = date.today().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE diseases SET ai_draft_date = %s WHERE slug = %s",
        (completed_at, normalized),
    )
    conn.commit()
    conn.close()
    return {
        "slug": normalized,
        "finalized": True,
        "coverage": "full",
        "doctors_count": doctors_count,
        "completed_at": completed_at,
    }


def update_disease_catalog_from_bootstrap(
    slug: str,
    *,
    name: str = "",
    name_short: str = "",
    omim: str = "",
    gene: str = "",
    inheritance: str = "",
    summary: str = "",
    prevalence_text: str = "",
    types: list[str] | None = None,
) -> None:
    """Apply non-empty bootstrap metadata to an existing disease row.

    Bootstrap only INSERTs on first create; repeat runs (or a row created with
    minimal fields) must still receive summary / inheritance / gene from the
    lookup form payload.
    """
    normalized = normalize_disease_slug(slug)
    if normalized is None:
        return
    assignments: list[str] = []
    params: list[Any] = []
    for column, value in (
        ("name", name),
        ("name_short", name_short),
        ("omim", omim),
        ("gene", gene),
        ("inheritance", inheritance),
        ("summary", summary),
        ("prevalence_text", prevalence_text),
    ):
        text = str(value or "").strip()
        if text:
            assignments.append(f"{column} = %s")
            params.append(text)
    if types:
        cleaned = [str(t).strip() for t in types if str(t).strip()]
        if cleaned:
            assignments.append("types_json = %s")
            params.append(json.dumps(cleaned, ensure_ascii=False))
    if not assignments:
        return
    params.append(normalized)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE diseases SET {', '.join(assignments)} WHERE slug = %s",
        params,
    )
    conn.commit()
    conn.close()


def get_disease_by_slug(
    slug: str,
    *,
    include_prompt_profile: bool = False,
) -> dict[str, Any] | None:
    """Load disease by slug. Prompt profile is omitted unless explicitly requested (internal pipelines)."""
    normalized = normalize_disease_slug(slug)
    if normalized is None:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM diseases WHERE slug = %s", (normalized,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_disease(row, include_prompt_profile=include_prompt_profile)


# Trial statuses counted as "active recruiting" on the public home view.
_CATALOG_ACTIVE_TRIAL_STATUSES = ("recruiting", "active_not_recruiting")
# Guideline PR statuses still awaiting review.
_CATALOG_OPEN_PR_STATUSES = ("pending", "under-review")


def compute_live_catalog_stats(*, doctor_count: int = 0) -> dict[str, int]:
    """Aggregate counters from live catalog tables (not the seed snapshot row)."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Catalog index counter: visible (listed=1) diseases only (RES-1).
        cur.execute("SELECT COUNT(*) AS n FROM diseases WHERE listed = 1")
        disease_count = int(cur.fetchone()["n"])

        recruiting_trial_count = 0
        if table_exists(conn, "trials"):
            cur.execute(
                "SELECT COUNT(*) AS n FROM trials WHERE status = ANY(%s)",
                (list(_CATALOG_ACTIVE_TRIAL_STATUSES),),
            )
            recruiting_trial_count = int(cur.fetchone()["n"])

        open_pr_count = 0
        if table_exists(conn, "content_prs"):
            cur.execute(
                "SELECT COUNT(*) AS n FROM content_prs WHERE status = ANY(%s)",
                (list(_CATALOG_OPEN_PR_STATUSES),),
            )
            open_pr_count = int(cur.fetchone()["n"])
    finally:
        conn.close()

    return {
        "diseaseCount": disease_count,
        "doctorCount": max(0, int(doctor_count)),
        "recruitingTrialCount": recruiting_trial_count,
        "openPrCount": open_pr_count,
    }


def get_catalog_stats() -> dict[str, int]:
    """Return live catalog counters for the public home page."""
    return compute_live_catalog_stats()



def upsert_guideline_document(
    *,
    disease_slug: str,
    document: dict[str, Any],
    version: str,
    section_count: int,
    last_reviewed: str | None,
) -> None:
    """Insert or replace one row in ``guideline_documents``.

    Used by the post-run publish bridge to land a fresh AI-draft document
    after a successful PubMed pipeline run, and by future publish flows.
    ``document`` is the dict that round-trips through
    :class:`backend.content_models.GuidelineDocumentResponse` — callers are
    expected to have validated it already.
    """
    normalized = normalize_disease_slug(disease_slug)
    if normalized is None:
        raise ValueError(f"invalid disease_slug: {disease_slug!r}")
    payload = json.dumps(document, ensure_ascii=False)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO guideline_documents (
            disease_slug, version, locale, section_count, last_reviewed, sections_json
        ) VALUES (%s, %s, 'en', %s, %s, %s)
        ON CONFLICT (disease_slug) DO UPDATE SET
            version = excluded.version,
            section_count = excluded.section_count,
            last_reviewed = excluded.last_reviewed,
            sections_json = excluded.sections_json
        """,
        (normalized, version, int(section_count), last_reviewed, payload),
    )
    conn.commit()
    conn.close()

def sync_guideline_document_bodies_from_file() -> None:
    """Backfill full guideline JSON bodies when sections_json is still empty."""
    path = Path(GUIDELINE_BODIES_PATH)
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    conn = get_connection()
    cur = conn.cursor()
    for slug, document in data.items():
        normalized = normalize_disease_slug(slug)
        if normalized is None or not isinstance(document, dict):
            continue
        cur.execute(
            "SELECT sections_json FROM guideline_documents WHERE disease_slug = %s",
            (normalized,),
        )
        row = cur.fetchone()
        if row is None:
            continue
        existing = row["sections_json"]
        if existing is not None and str(existing).strip():
            continue
        cur.execute(
            """
            UPDATE guideline_documents
            SET sections_json = %s
            WHERE disease_slug = %s
            """,
            (json.dumps(document, ensure_ascii=False), normalized),
        )
    conn.commit()
    conn.close()


def get_guideline_document(disease_slug: str) -> dict[str, Any] | None:
    """Full living guideline document for the public reader (English)."""
    normalized = normalize_disease_slug(disease_slug)
    if normalized is None:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT sections_json FROM guideline_documents WHERE disease_slug = %s",
        (normalized,),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    raw = row["sections_json"]
    if raw is None or not str(raw).strip():
        sync_guideline_document_bodies_from_file()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT sections_json FROM guideline_documents WHERE disease_slug = %s",
            (normalized,),
        )
        row = cur.fetchone()
        conn.close()
        if row is None:
            return None
        raw = row["sections_json"]
    if raw is None or not str(raw).strip():
        return None
    return json.loads(raw)


def get_guideline_meta(disease_slug: str) -> dict[str, Any] | None:
    normalized = normalize_disease_slug(disease_slug)
    if normalized is None:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT disease_slug, version, locale, section_count, last_reviewed
        FROM guideline_documents
        WHERE disease_slug = %s
        """,
        (normalized,),
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "diseaseSlug": row["disease_slug"],
        "version": row["version"],
        "locale": row["locale"],
        "sectionCount": row["section_count"],
        "lastReviewed": row["last_reviewed"],
    }


def seed_care_pathways_from_file() -> None:
    """Seed care_pathways for diseases missing a row (e.g. fd from Boyce reference tree)."""
    path = Path(CARE_PATHWAY_SEED_PATH)
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return
    conn = get_connection()
    cur = conn.cursor()
    today = date.today().isoformat()
    for slug, tree in data.items():
        normalized = normalize_disease_slug(str(slug))
        if normalized is None or not isinstance(tree, dict):
            continue
        cur.execute("SELECT 1 FROM care_pathways WHERE disease_slug = %s", (normalized,))
        if cur.fetchone() is not None:
            continue
        cur.execute("SELECT 1 FROM diseases WHERE slug = %s", (normalized,))
        if cur.fetchone() is None:
            continue
        meta = get_guideline_meta(normalized)
        cur.execute(
            """
            INSERT INTO care_pathways (
                disease_slug, locale, version, based_on, generated_at,
                source_guideline_version, source_execution_id, tree_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                normalized,
                str(tree.get("locale") or "en"),
                "v1.0-seed",
                str(tree.get("basedOn") or "Reference pathway seed"),
                today,
                meta.get("version") if meta else None,
                None,
                json.dumps(tree, ensure_ascii=False),
            ),
        )
    conn.commit()
    conn.close()


def seed_trials_from_file() -> None:
    """Load content_trials_seed.json on a fresh DB (or top up missing rows).

    Idempotent: ``INSERT`` for the ``trials`` table and the
    ``disease_trials`` junction makes it safe to call on every startup.
    Trials whose ``diseases`` list references a slug we have not seeded
    are still inserted into ``trials`` (so /api/trials returns them),
    just without a junction row. ON CONFLICT DO NOTHING"""
    path = Path(TRIALS_SEED_PATH)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    rows = data.get("trials") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return
    conn = get_connection()
    cur = conn.cursor()
    known_slugs = {
        str(r["slug"])
        for r in cur.execute("SELECT slug FROM diseases").fetchall()
    }
    for trial in rows:
        if not isinstance(trial, dict):
            continue
        nct = str(trial.get("nct") or "").strip()
        if not nct:
            continue
        cur.execute(
            """
            INSERT INTO trials (
                nct, title, phase, status, sponsor, city, country,
                lat, lng, age_range, principal_investigator,
                eligibility_summary, enrollment_target, enrolled,
                contact, last_seen
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            (
                nct,
                str(trial.get("title") or ""),
                str(trial.get("phase") or ""),
                str(trial.get("status") or ""),
                str(trial.get("sponsor") or ""),
                trial.get("city"),
                trial.get("country"),
                trial.get("lat"),
                trial.get("lng"),
                trial.get("ageRange"),
                trial.get("principalInvestigator"),
                str(trial.get("eligibilitySummary") or ""),
                trial.get("enrollmentTarget"),
                trial.get("enrolled"),
                trial.get("contact"),
                trial.get("lastSeen"),
            ),
        )
        for slug in trial.get("diseases", []) or []:
            slug_str = str(slug).strip().lower()
            if not slug_str or slug_str not in known_slugs:
                continue
            cur.execute(
                "INSERT INTO disease_trials (disease_slug, nct) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (slug_str, nct),
            )
    conn.commit()
    conn.close()


def seed_therapies_from_file() -> None:
    """Seed therapies for each disease present in content_therapies_seed.json.

    Idempotent on a per-(slug, name) basis: rows whose ``(disease_slug, name)``
    pair already exists are not re-inserted. The order from the JSON file is
    preserved by writing the file index into ``sort_order``.
    """
    path = Path(THERAPIES_SEED_PATH)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    payload = data.get("therapies") if isinstance(data, dict) else None
    if not isinstance(payload, dict):
        return
    conn = get_connection()
    cur = conn.cursor()
    known_slugs = {
        str(r["slug"])
        for r in cur.execute("SELECT slug FROM diseases").fetchall()
    }
    for raw_slug, items in payload.items():
        slug = str(raw_slug).strip().lower()
        if not slug or slug not in known_slugs or not isinstance(items, list):
            continue
        for index, therapy in enumerate(items):
            if not isinstance(therapy, dict):
                continue
            name = str(therapy.get("name") or "").strip()
            status = str(therapy.get("status") or "").strip()
            if not name or status not in (
                "consensus",
                "verified",
                "pending",
                "preclinical",
            ):
                continue
            note = str(therapy.get("note") or "")
            cur.execute(
                "SELECT id FROM therapies WHERE disease_slug = %s AND name = %s",
                (slug, name),
            )
            existing = cur.fetchone()
            if existing is not None:
                # Re-apply the seed text on every boot. The seed file is the
                # source of truth; if a clinician edits notes via an admin
                # tool we will need a dirty flag — Phase 2 concern.
                cur.execute(
                    """
                    UPDATE therapies
                    SET status = %s, note = %s, sort_order = %s
                    WHERE id = %s
                    """,
                    (status, note, index, int(existing["id"])),
                )
                continue
            cur.execute(
                """
                INSERT INTO therapies (disease_slug, name, status, note, sort_order)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (slug, name, status, note, index),
            )
    conn.commit()
    conn.close()


def seed_foundations_from_file() -> None:
    """Seed foundations + disease_foundations from content_foundations_seed.json.

    Idempotent: foundations have a UNIQUE constraint on ``name`` so the
    upsert is ``INSERT``; junction rows use the same approach. ON CONFLICT DO NOTHING"""
    path = Path(FOUNDATIONS_SEED_PATH)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    rows = data.get("foundations") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return
    conn = get_connection()
    cur = conn.cursor()
    known_slugs = {
        str(r["slug"])
        for r in cur.execute("SELECT slug FROM diseases").fetchall()
    }
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        cur.execute(
            """
            INSERT INTO foundations (
                name, scope, url, city, country, services_json, source
            ) VALUES (%s, %s, %s, %s, %s, %s, 'seed') ON CONFLICT DO NOTHING""",
            (
                name,
                str(item.get("scope") or ""),
                str(item.get("url") or ""),
                item.get("city"),
                item.get("country"),
                json.dumps(item.get("services") or [], ensure_ascii=False),
            ),
        )
        cur.execute("SELECT id FROM foundations WHERE name = %s", (name,))
        row = cur.fetchone()
        if row is None:
            continue
        foundation_id = int(row["id"])
        for slug in item.get("diseases", []) or []:
            slug_str = str(slug).strip().lower()
            if not slug_str or slug_str not in known_slugs:
                continue
            cur.execute(
                "INSERT INTO disease_foundations (disease_slug, foundation_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (slug_str, foundation_id),
            )
    conn.commit()
    conn.close()


def seed_official_guidelines_from_file() -> None:
    """Seed official_guideline_pointers for each disease the seed file names.

    Idempotent. The seed marks every row as ``source = 'seed'`` so a future
    reviewer-confirmed entry (``source = 'reviewer'``) clearly differs from
    the bundled defaults — and the discovery workflow's auto-suggestions
    (``source = 'workflow'``) are visibly the third class.
    """
    path = Path(OFFICIAL_GUIDELINES_SEED_PATH)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    pointers = data.get("pointers") if isinstance(data, dict) else None
    if not isinstance(pointers, dict):
        return
    conn = get_connection()
    cur = conn.cursor()
    known_slugs = {
        str(r["slug"])
        for r in cur.execute("SELECT slug FROM diseases").fetchall()
    }
    now = date.today().isoformat()
    for raw_slug, entry in pointers.items():
        slug = str(raw_slug).strip().lower()
        if not slug or slug not in known_slugs or not isinstance(entry, dict):
            continue
        cur.execute(
            "SELECT 1 FROM official_guideline_pointers WHERE disease_slug = %s",
            (slug,),
        )
        if cur.fetchone() is not None:
            continue
        cur.execute(
            """
            INSERT INTO official_guideline_pointers (
                disease_slug, title, authors, year, journal, pmid, url,
                summary, confirmed_by, confirmed_at, source
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                slug,
                str(entry.get("title") or ""),
                str(entry.get("authors") or ""),
                int(entry.get("year") or 0),
                str(entry.get("journal") or ""),
                str(entry.get("pmid") or ""),
                str(entry.get("url") or ""),
                str(entry.get("summary") or ""),
                str(entry.get("confirmed_by") or ""),
                now,
                str(entry.get("source") or "seed"),
            ),
        )
    conn.commit()
    conn.close()


def _is_published_pathway_tree(tree: dict[str, Any]) -> bool:
    """False for placeholder rows saved before the first publish."""
    if not tree.get("children"):
        return False
    title = str(tree.get("title") or "").strip().lower()
    return title not in ("pending", "unpublished")


def _pathway_row_to_dict(row: Any) -> dict[str, Any]:
    tree = json.loads(row["tree_json"])
    return {
        "diseaseSlug": row["disease_slug"],
        "locale": row["locale"],
        "version": row["version"],
        "basedOn": row["based_on"],
        "generatedAt": row["generated_at"],
        "sourceGuidelineVersion": row["source_guideline_version"],
        "sourceRunId": row["source_execution_id"],
        "tree": tree,
        "hasDraft": bool(row["draft_tree_json"]) if "draft_tree_json" in row.keys() else False,
    }


def _fetch_pathway_row(cur: Any, normalized: str) -> Any | None:
    cur.execute(
        """
        SELECT disease_slug, locale, version, based_on, generated_at,
               source_guideline_version, source_execution_id, tree_json,
               draft_tree_json, draft_updated_at
        FROM care_pathways
        WHERE disease_slug = %s
        """,
        (normalized,),
    )
    return cur.fetchone()


def get_parent_pathway(disease_slug: str) -> dict[str, Any] | None:
    """Return published parent care pathway for a disease (public API)."""
    normalized = normalize_disease_slug(disease_slug)
    if normalized is None:
        return None
    conn = get_connection()
    cur = conn.cursor()
    row = _fetch_pathway_row(cur, normalized)
    conn.close()
    if row is None:
        seed_care_pathways_from_file()
        conn = get_connection()
        cur = conn.cursor()
        row = _fetch_pathway_row(cur, normalized)
        conn.close()
    if row is None:
        return None
    payload = _pathway_row_to_dict(row)
    if not _is_published_pathway_tree(payload["tree"]):
        return None
    payload.pop("hasDraft", None)
    return payload


def get_parent_pathway_draft(disease_slug: str) -> dict[str, Any] | None:
    """Return draft pathway metadata and tree for operator preview."""
    normalized = normalize_disease_slug(disease_slug)
    if normalized is None:
        return None
    conn = get_connection()
    cur = conn.cursor()
    row = _fetch_pathway_row(cur, normalized)
    conn.close()
    if row is None or not row["draft_tree_json"]:
        return None
    tree = json.loads(row["draft_tree_json"])
    return {
        "diseaseSlug": row["disease_slug"],
        "locale": row["locale"],
        "version": row["version"],
        "basedOn": row["based_on"],
        "generatedAt": row["draft_updated_at"] or row["generated_at"],
        "sourceGuidelineVersion": row["source_guideline_version"],
        "sourceRunId": row["source_execution_id"],
        "tree": tree,
    }


def save_parent_pathway(
    disease_slug: str,
    tree: dict[str, Any],
    *,
    version: str,
    based_on: str,
    locale: str = "en",
    source_guideline_version: str | None = None,
    source_execution_id: str | None = None,
) -> dict[str, Any]:
    """Save validated patient pathway chart as draft (not public until publish)."""
    normalized = normalize_disease_slug(disease_slug)
    if normalized is None:
        raise ValueError("Invalid disease slug.")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM diseases WHERE slug = %s", (normalized,))
    if cur.fetchone() is None:
        conn.close()
        raise ValueError(f"Disease '{normalized}' not found in catalog.")
    draft_updated_at = date.today().isoformat()
    cur.execute("SELECT tree_json FROM care_pathways WHERE disease_slug = %s", (normalized,))
    existing = cur.fetchone()
    placeholder_tree = json.dumps({"id": "root", "title": "Pending", "children": []})
    if existing is None:
        cur.execute(
            """
            INSERT INTO care_pathways (
                disease_slug, locale, version, based_on, generated_at,
                source_guideline_version, source_execution_id, tree_json,
                draft_tree_json, draft_updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                normalized,
                locale,
                version,
                based_on,
                draft_updated_at,
                source_guideline_version,
                source_execution_id,
                placeholder_tree,
                json.dumps(tree, ensure_ascii=False),
                draft_updated_at,
            ),
        )
    else:
        cur.execute(
            """
            UPDATE care_pathways SET
                locale = %s,
                version = %s,
                based_on = %s,
                source_guideline_version = %s,
                source_execution_id = %s,
                draft_tree_json = %s,
                draft_updated_at = %s
            WHERE disease_slug = %s
            """,
            (
                locale,
                version,
                based_on,
                source_guideline_version,
                source_execution_id,
                json.dumps(tree, ensure_ascii=False),
                draft_updated_at,
                normalized,
            ),
        )
    conn.commit()
    conn.close()
    return get_parent_pathway_draft(normalized) or {}


def publish_parent_pathway(disease_slug: str) -> dict[str, Any]:
    """Promote draft patient pathway chart to the version served on the public site."""
    normalized = normalize_disease_slug(disease_slug)
    if normalized is None:
        raise ValueError("Invalid disease slug.")
    conn = get_connection()
    cur = conn.cursor()
    row = _fetch_pathway_row(cur, normalized)
    if row is None or not row["draft_tree_json"]:
        conn.close()
        raise ValueError(
            f"No draft patient pathway for '{normalized}'. "
            "Run the patient chart pipeline and save a draft before publishing."
        )
    published_at = date.today().isoformat()
    cur.execute(
        """
        UPDATE care_pathways SET
            tree_json = draft_tree_json,
            generated_at = %s
        WHERE disease_slug = %s
        """,
        (published_at, normalized),
    )
    conn.commit()
    conn.close()
    published = get_parent_pathway(normalized)
    if published is None:
        raise ValueError(f"Publish failed for '{normalized}' — pathway row missing after update.")
    return published


def build_parent_pathway_context(disease_slug: str) -> dict[str, Any]:
    """Evidence bundle for LLM pathway synthesis."""
    normalized = normalize_disease_slug(disease_slug)
    if normalized is None:
        return {"ok": False, "error": "Invalid disease slug."}
    disease = get_disease_by_slug(normalized, include_prompt_profile=True)
    if disease is None:
        return {"ok": False, "error": f"Disease '{normalized}' not found."}
    document = get_guideline_document(normalized)
    if document is None:
        return {
            "ok": False,
            "error": (
                "No published guideline document for this disease. "
                "Run guideline generation and publish sections before generating a patient chart."
            ),
        }
    meta = get_guideline_meta(normalized)
    # Prefer diagnosis / genetics / first-line workup for parent "first steps" synthesis.
    priority_ids = ("diagnosis", "histopathology", "monitoring", "therapy", "surgery")
    excerpts: list[str] = []
    allowed_pmids: list[str] = []
    sections = [s for s in (document.get("sections") or []) if isinstance(s, dict)]

    def _section_sort_key(section: dict[str, Any]) -> tuple[int, str]:
        sid = str(section.get("id") or "").lower()
        for idx, pid in enumerate(priority_ids):
            if sid == pid or pid in sid:
                return (idx, sid)
        if "diag" in sid or "genet" in sid or "confirm" in sid:
            return (0, sid)
        if "treat" in sid:
            return (3, sid)
        return (9, sid)

    for section in sorted(sections, key=_section_sort_key):
        sid = str(section.get("id") or "")
        if sid and not any(
            token in sid for token in (*priority_ids, "diag", "genet", "treat", "monitor", "surg")
        ):
            continue
        title = str(section.get("title") or sid)
        excerpts.append(f"## {title}")
        intro = str(section.get("intro") or "").strip()
        if intro:
            excerpts.append(intro)
        for para in section.get("paragraphs") or []:
            if not isinstance(para, dict):
                continue
            text = str(para.get("text") or "").strip()
            if text:
                excerpts.append(text)
            for pmid in para.get("citations") or []:
                p = str(pmid).strip()
                if p and p not in allowed_pmids:
                    allowed_pmids.append(p)
    return {
        "ok": True,
        "disease_slug": normalized,
        "disease_name": disease.get("name") or normalized,
        "guideline_version": (meta or {}).get("version"),
        "guideline_based_on": document.get("basedOn") or "",
        "allowed_pmids": allowed_pmids,
        "evidence_excerpt": "\n\n".join(excerpts)[:24_000],
        "profile": disease.get("guidelinePromptProfile") or {},
        "pathway_product_brief": (
            "Patient-facing pathway: a short, scannable checklist grounded in the published guideline — "
            "what to do first, who to see, what to ask, when to call. Audience may include **adults diagnosed "
            "with the condition**, **parents of affected children**, or **other caregivers** — do not assume a "
            "paediatric patient unless the evidence is clearly child-only. Each line must differ in meaning; "
            "no copy-pasted boilerplate. Length is capped server-side: prioritise clarity and usefulness "
            "for overwhelmed patients and families."
        ),
    }
