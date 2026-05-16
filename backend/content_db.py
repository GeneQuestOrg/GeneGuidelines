"""SQLite access for public diseases and guideline metadata (Phase 4)."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

try:
    from .config import BACKEND_DIR
    from .database import get_connection
    from .guideline_prompt_profile import (
        empty_guideline_prompt_profile,
        normalize_guideline_prompt_profile,
    )
except ImportError:
    from config import BACKEND_DIR
    from database import get_connection
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
            guideline_prompt_profile_json TEXT NOT NULL DEFAULT '{}'
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
            disease_slug TEXT PRIMARY KEY REFERENCES diseases(slug) ON DELETE CASCADE,
            locale TEXT NOT NULL DEFAULT 'en',
            version TEXT NOT NULL,
            based_on TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            source_guideline_version TEXT,
            source_execution_id TEXT,
            tree_json TEXT NOT NULL
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            disease_slug TEXT NOT NULL REFERENCES diseases(slug) ON DELETE CASCADE,
            name TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('consensus','verified','pending','preclinical')),
            note TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 100
        )
        """
    )
    conn.commit()
    conn.close()
    ensure_guideline_prompt_column()
    ensure_care_pathway_draft_columns()
    sync_guideline_document_bodies_from_file()
    # NOTE: content_prs and disease_trials have FKs to diseases(slug); their
    # seeders (seed_content_prs_if_empty / seed_trials_from_file) are invoked
    # from database.init_db() AFTER seed_content_if_empty() so the parent
    # rows exist. Keeping those calls here would fire them on an empty
    # diseases table and skip the junction inserts silently.
    seed_care_pathways_from_file()


def ensure_care_pathway_draft_columns() -> None:
    """Add draft_tree_json for operator preview before publish."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(care_pathways)")
    columns = {row["name"] for row in cur.fetchall()}
    if "draft_tree_json" not in columns:
        cur.execute("ALTER TABLE care_pathways ADD COLUMN draft_tree_json TEXT")
    if "draft_updated_at" not in columns:
        cur.execute("ALTER TABLE care_pathways ADD COLUMN draft_updated_at TEXT")
    conn.commit()
    conn.close()


def ensure_guideline_prompt_column() -> None:
    """Add guideline_prompt_profile_json to diseases if missing (existing deployments)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(diseases)")
    columns = {row["name"] for row in cur.fetchall()}
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
            "SELECT guideline_prompt_profile_json FROM diseases WHERE slug = ?",
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
            "UPDATE diseases SET guideline_prompt_profile_json = ? WHERE slug = ?",
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ) VALUES (?, ?, ?, ?, ?)
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
        ) VALUES (1, ?, ?, ?, ?)
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
            INSERT OR IGNORE INTO content_prs (
                id, disease_slug, title, opened, status, author, reviewer,
                summary, citations_count, diff_json, papers_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
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
        clauses.append("status = ?")
        params.append(status)
    if disease_slug is not None:
        normalized = normalize_disease_slug(disease_slug)
        if normalized is not None:
            clauses.append("disease_slug = ?")
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
    cur.execute("SELECT * FROM content_prs WHERE id = ?", (normalized,))
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
        "SELECT disease_slug, reviewer, status FROM content_prs WHERE id = ?",
        (normalized,),
    )
    pr_row = cur.fetchone()
    if pr_row is None:
        conn.close()
        return None

    reviewer_value = _reviewer_name(reviewer, pr_row["reviewer"])
    disease_slug = pr_row["disease_slug"]

    cur.execute(
        "SELECT sections_json FROM guideline_documents WHERE disease_slug = ?",
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
        SET sections_json = ?, last_reviewed = ?
        WHERE disease_slug = ?
        """,
        (json.dumps(updated_doc, ensure_ascii=False), _today_iso_for_pr(), disease_slug),
    )
    cur.execute(
        """
        UPDATE content_prs
        SET status = 'verified', reviewer = ?
        WHERE id = ?
        """,
        (reviewer_value, normalized),
    )
    conn.commit()
    cur.execute("SELECT * FROM content_prs WHERE id = ?", (normalized,))
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
        cur.execute("SELECT reviewer FROM content_prs WHERE id = ?", (normalized,))
        row = cur.fetchone()
        if row is None:
            conn.close()
            return None
        reviewer_value = _reviewer_name(reviewer, row["reviewer"])
        cur.execute(
            """
            UPDATE content_prs
            SET status = 'rejected', reviewer = ?
            WHERE id = ?
            """,
            (reviewer_value, normalized),
        )
        conn.commit()
        cur.execute("SELECT * FROM content_prs WHERE id = ?", (normalized,))
        updated = cur.fetchone()
        conn.close()
        if updated is None:
            return None
        return _row_to_pr_detail(updated)

    if action in ("request_changes", "request-changes"):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT reviewer FROM content_prs WHERE id = ?", (normalized,))
        row = cur.fetchone()
        if row is None:
            conn.close()
            return None
        reviewer_value = _reviewer_name(reviewer, row["reviewer"])
        cur.execute(
            """
            UPDATE content_prs
            SET status = 'under-review', reviewer = ?
            WHERE id = ?
            """,
            (reviewer_value, normalized),
        )
        conn.commit()
        cur.execute("SELECT * FROM content_prs WHERE id = ?", (normalized,))
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
    cur.execute("SELECT 1 FROM diseases WHERE slug = ?", (normalized,))
    if cur.fetchone() is None:
        conn.close()
        return None
    payload = normalize_guideline_prompt_profile(profile)
    cur.execute(
        "UPDATE diseases SET guideline_prompt_profile_json = ? WHERE slug = ?",
        (json.dumps(payload, ensure_ascii=False), normalized),
    )
    conn.commit()
    cur.execute("SELECT * FROM diseases WHERE slug = ?", (normalized,))
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
        ORDER BY name COLLATE NOCASE
        """
    )
    rows = cur.fetchall()
    conn.close()
    return [_row_to_disease_list_item(r) for r in rows]


def list_diseases() -> list[dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM diseases ORDER BY name COLLATE NOCASE")
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
    cur.execute("SELECT * FROM diseases WHERE slug = ?", (normalized,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_disease(row, include_prompt_profile=include_prompt_profile)


def get_catalog_stats() -> dict[str, int]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM catalog_stats WHERE id = 1")
    row = cur.fetchone()
    if row is None:
        cur.execute("SELECT COUNT(*) AS n FROM diseases")
        disease_count = int(cur.fetchone()["n"])
        conn.close()
        return {
            "diseaseCount": disease_count,
            "doctorCount": 0,
            "recruitingTrialCount": 0,
            "openPrCount": 0,
        }
    conn.close()
    return {
        "diseaseCount": row["disease_count"],
        "doctorCount": row["doctor_count"],
        "recruitingTrialCount": row["recruiting_trial_count"],
        "openPrCount": row["open_pr_count"],
    }


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
            "SELECT sections_json FROM guideline_documents WHERE disease_slug = ?",
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
            SET sections_json = ?
            WHERE disease_slug = ?
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
        "SELECT sections_json FROM guideline_documents WHERE disease_slug = ?",
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
            "SELECT sections_json FROM guideline_documents WHERE disease_slug = ?",
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
        WHERE disease_slug = ?
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
        cur.execute("SELECT 1 FROM care_pathways WHERE disease_slug = ?", (normalized,))
        if cur.fetchone() is not None:
            continue
        cur.execute("SELECT 1 FROM diseases WHERE slug = ?", (normalized,))
        if cur.fetchone() is None:
            continue
        meta = get_guideline_meta(normalized)
        cur.execute(
            """
            INSERT INTO care_pathways (
                disease_slug, locale, version, based_on, generated_at,
                source_guideline_version, source_execution_id, tree_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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

    Idempotent: ``INSERT OR IGNORE`` for the ``trials`` table and the
    ``disease_trials`` junction makes it safe to call on every startup.
    Trials whose ``diseases`` list references a slug we have not seeded
    are still inserted into ``trials`` (so /api/trials returns them),
    just without a junction row.
    """
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
            INSERT OR IGNORE INTO trials (
                nct, title, phase, status, sponsor, city, country,
                lat, lng, age_range, principal_investigator,
                eligibility_summary, enrollment_target, enrolled,
                contact, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
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
                "INSERT OR IGNORE INTO disease_trials (disease_slug, nct) VALUES (?, ?)",
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
            cur.execute(
                "SELECT 1 FROM therapies WHERE disease_slug = ? AND name = ?",
                (slug, name),
            )
            if cur.fetchone() is not None:
                continue
            cur.execute(
                """
                INSERT INTO therapies (disease_slug, name, status, note, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    slug,
                    name,
                    status,
                    str(therapy.get("note") or ""),
                    index,
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
        WHERE disease_slug = ?
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
    cur.execute("SELECT 1 FROM diseases WHERE slug = ?", (normalized,))
    if cur.fetchone() is None:
        conn.close()
        raise ValueError(f"Disease '{normalized}' not found in catalog.")
    draft_updated_at = date.today().isoformat()
    cur.execute("SELECT tree_json FROM care_pathways WHERE disease_slug = ?", (normalized,))
    existing = cur.fetchone()
    placeholder_tree = json.dumps({"id": "root", "title": "Pending", "children": []})
    if existing is None:
        cur.execute(
            """
            INSERT INTO care_pathways (
                disease_slug, locale, version, based_on, generated_at,
                source_guideline_version, source_execution_id, tree_json,
                draft_tree_json, draft_updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                locale = ?,
                version = ?,
                based_on = ?,
                source_guideline_version = ?,
                source_execution_id = ?,
                draft_tree_json = ?,
                draft_updated_at = ?
            WHERE disease_slug = ?
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
            generated_at = ?
        WHERE disease_slug = ?
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
