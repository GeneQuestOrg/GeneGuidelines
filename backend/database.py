"""
SQLite database – clean schema, init, seed from JSON (only when tables are empty).
"""
import json
import sqlite3
import re
from datetime import datetime
from pathlib import Path

try:
    from .config import DB_PATH, SEED_DATA_PATH
    from .flows.pubmed.code_nodes import PM4_BUILD_SOURCE, PM5_SOURCE, PM_GATE_SOURCE, PM_MERGE_SOURCE
    from .guideline_prompt_profile import append_disease_prompt_block
except ImportError:
    from config import DB_PATH, SEED_DATA_PATH
    from flows.pubmed.code_nodes import PM4_BUILD_SOURCE, PM5_SOURCE, PM_GATE_SOURCE, PM_MERGE_SOURCE
    from guideline_prompt_profile import append_disease_prompt_block


def _row_to_dict(cursor, row):
    """Row factory: zwraca dict z kluczami = nazwy kolumn (dla JSON / Pydantic)."""
    if cursor.description is None:
        return {}
    return {cursor.description[i][0]: row[i] for i in range(len(row))}


# Higher timeout + WAL reduce "database is locked" when multiple requests hit DB (e.g. add node + refresh).
SQLITE_TIMEOUT = 20.0


def get_connection():
    """Return SQLite connection. WAL + higher timeout reduce lock contention."""
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT)
    conn.row_factory = _row_to_dict
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# Circular-import safe: database_flow_ensures imports get_connection which is already defined above.
try:
    from .database_flow_ensures import (
        _ensure_doctor_finder_flow,
        _ensure_doctor_finder_geo_node,
        _PARENT_PATHWAY_FLOW_DEFINITION_INSERT_SQL,
        _parent_pathway_flow_definition_insert_params,
        _ensure_parent_pathway_flow,
        _upgrade_parent_pathway_flow_add_plan_node,
        _sync_parent_pathway_synth_prompt_from_disk,
        _sync_parent_pathway_plan_prompt_from_disk,
    )
except ImportError:
    from database_flow_ensures import (
        _ensure_doctor_finder_flow,
        _ensure_doctor_finder_geo_node,
        _PARENT_PATHWAY_FLOW_DEFINITION_INSERT_SQL,
        _parent_pathway_flow_definition_insert_params,
        _ensure_parent_pathway_flow,
        _upgrade_parent_pathway_flow_add_plan_node,
        _sync_parent_pathway_synth_prompt_from_disk,
        _sync_parent_pathway_plan_prompt_from_disk,
    )


def init_db():
    """Create tables only. No migrations, no cleanup, no data."""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'not_started',
            resolution_summary TEXT,
            diagnostic_steps TEXT,
            reporter_name TEXT NOT NULL DEFAULT 'User',
            category TEXT NOT NULL DEFAULT 'General',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
            author TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tool_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL DEFAULT 'General',
            execution_mode TEXT NOT NULL DEFAULT 'auto',
            scope TEXT NOT NULL DEFAULT 'operational',
            enabled INTEGER NOT NULL DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tool_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'requested',
            similarity_key TEXT,
            note TEXT,
            ticket_id INTEGER REFERENCES tickets(id),
            builder_agent_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tool_implementations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pr_created',
            pr_number TEXT,
            pr_url TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS flow_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flow_key TEXT NOT NULL,
            node_id TEXT NOT NULL,
            node_type TEXT NOT NULL,
            label TEXT NOT NULL,
            description TEXT,
            prompt TEXT,
            loop_policy TEXT DEFAULT 'none',
            execution_policy TEXT DEFAULT 'auto',
            max_retry INTEGER DEFAULT 3,
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            position_x REAL,
            position_y REAL,
            prompt_mode TEXT NOT NULL DEFAULT 'agentic',
            model_name TEXT,
            output_schema_key TEXT,
            output_schema TEXT,
            agentic_step_close INTEGER NOT NULL DEFAULT 0,
            python_source TEXT,
            http_url TEXT,
            http_method TEXT,
            http_headers TEXT,
            http_body TEXT,
            UNIQUE(flow_key, node_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS flow_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flow_key TEXT NOT NULL,
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            label TEXT,
            UNIQUE(flow_key, source_node_id, target_node_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS _seed_done (
            version TEXT PRIMARY KEY
        )
    """)

    conn.commit()
    conn.close()
    _ensure_position_columns()
    _ensure_flow_execution_columns()
    _ensure_output_schema_column()
    _ensure_agentic_step_close_column()
    _ensure_python_source_column()
    _ensure_step_name_column()
    _ensure_http_request_columns()
    _ensure_rag_assist_columns()
    _ensure_merge_columns()
    _ensure_integration_columns()
    _ensure_flow_edge_label_column()
    _ensure_guidelines_rag_column()
    _ensure_flow_texts_english()
    _ensure_pubmed_flow()
    _ensure_pubmed_eval_tail()
    _ensure_pubmed_seed_ticket_wording()
    _ensure_doctor_finder_flow()
    _ensure_doctor_finder_geo_node()
    _ensure_parent_pathway_flow()
    _upgrade_parent_pathway_flow_add_plan_node()
    _sync_parent_pathway_synth_prompt_from_disk()
    _sync_parent_pathway_plan_prompt_from_disk()
    try:
        from .content_db import (
            ensure_content_schema,
            seed_content_if_empty,
            seed_content_prs_if_empty,
            seed_foundations_from_file,
            seed_official_guidelines_from_file,
            seed_therapies_from_file,
            seed_trials_from_file,
        )
    except ImportError:
        from content_db import (  # type: ignore[no-redef]
            ensure_content_schema,
            seed_content_if_empty,
            seed_content_prs_if_empty,
            seed_foundations_from_file,
            seed_official_guidelines_from_file,
            seed_therapies_from_file,
            seed_trials_from_file,
        )
    ensure_content_schema()
    seed_content_if_empty()
    seed_content_prs_if_empty()
    seed_trials_from_file()
    seed_therapies_from_file()
    seed_foundations_from_file()
    seed_official_guidelines_from_file()
    try:
        from .guideline_run_store import ensure_guideline_run_results_schema
    except ImportError:
        from guideline_run_store import ensure_guideline_run_results_schema
    ensure_guideline_run_results_schema()
    try:
        from .doctor_finder_store import ensure_doctor_finder_run_results_schema
    except ImportError:
        from doctor_finder_store import ensure_doctor_finder_run_results_schema
    ensure_doctor_finder_run_results_schema()
    try:
        from .doctor_finder_store import repair_doctor_finder_catalog_slugs_from_disease_name
    except ImportError:
        from doctor_finder_store import repair_doctor_finder_catalog_slugs_from_disease_name
    repair_doctor_finder_catalog_slugs_from_disease_name()


def _ensure_pubmed_flow():
    """Upsert the current pubmed flow definition and required runtime tools."""
    _ensure_evaluation_source_nodes_column()
    conn = get_connection()
    cur = conn.cursor()
    now = datetime.now().isoformat()
    required_tools = [
        ("pubmed_search_articles", "Medical", "auto", "operational", 1),
        ("pubmed_fetch_article_details", "Medical", "auto", "operational", 1),
        ("pubmed_browser_search", "Medical", "auto", "operational", 1),
    ]
    for name, category, execution_mode, scope, enabled in required_tools:
        cur.execute("SELECT id FROM tool_catalog WHERE name = ?", (name,))
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO tool_catalog (name, category, execution_mode, scope, enabled) VALUES (?, ?, ?, ?, ?)",
                (name, category, execution_mode, scope, enabled),
            )

    cur.execute(
        "SELECT prompt FROM flow_definitions WHERE flow_key = 'pubmed' AND node_id = 'pm-1'"
    )
    pm1_row = cur.fetchone()
    cur.execute("SELECT COUNT(*) AS n FROM flow_definitions WHERE flow_key = 'pubmed'")
    pubmed_node_count = int(cur.fetchone()["n"])
    cur.execute(
        "SELECT 1 FROM flow_definitions WHERE flow_key = 'pubmed' AND node_id = 'pm_eval' LIMIT 1"
    )
    has_pm_eval = cur.fetchone() is not None
    if (
        pubmed_node_count >= 20
        and pm1_row
        and "context.initial.guideline_prompt_block" in (pm1_row.get("prompt") or "")
        and has_pm_eval
    ):
        conn.commit()
        conn.close()
        return

    pm2_source = """def run(context):
    outs = context.get("outputs", {})
    pm1 = outs.get("pm-1", {})

    def _safe_int(value, default=0):
        try:
            return int(value)
        except Exception:
            return default

    def _extract_pm1_payload(raw):
        import json

        data = {}
        if isinstance(raw, str) and raw.strip():
            try:
                data = json.loads(raw)
            except Exception:
                s = raw.strip()
                i = s.find("{")
                j = s.rfind("}")
                if i >= 0 and j > i:
                    try:
                        data = json.loads(s[i : j + 1])
                    except Exception:
                        data = {}
        return data if isinstance(data, dict) else {}

    def _normalize_core_fields(data, title_fallback=""):
        notes = []
        payload = data
        wrapped = payload.get("result")
        wrapped_alt = payload.get("results")
        if isinstance(wrapped, dict):
            notes.append("pm1_output_used_tool_envelope_result")
        if isinstance(wrapped_alt, dict):
            notes.append("pm1_output_used_tool_envelope_results")

        def pick(name, default):
            if name in payload:
                return payload.get(name)
            if isinstance(wrapped, dict) and name in wrapped:
                notes.append("field_from_result." + name)
                return wrapped.get(name)
            if isinstance(wrapped_alt, dict) and name in wrapped_alt:
                notes.append("field_from_results." + name)
                return wrapped_alt.get(name)
            return default

        core = {
            "query_text": str(pick("query_text", title_fallback) or title_fallback),
            "query_variants": pick("query_variants", []) or [],
            "fallback_used": bool(pick("fallback_used", False)),
            "retrieval_channel": str(pick("retrieval_channel", "primary_get") or "primary_get"),
            "fallback_reason": str(pick("fallback_reason", "none") or "none"),
            "total_found_estimate": _safe_int(pick("total_found_estimate", 0), 0),
            "total_requested": _safe_int(pick("total_requested", 0), 0),
            "total_analyzed": _safe_int(pick("total_analyzed", 0), 0),
            "total_with_abstract": _safe_int(pick("total_with_abstract", 0), 0),
            "request_count": _safe_int(pick("request_count", 0), 0),
            "http_status_stats": pick("http_status_stats", {}) or {},
            "evidence_manifest": pick("evidence_manifest", {}) or {},
            "articles_in": pick("articles", []) or [],
            "cards_in": pick("evidence_cards", []) or [],
        }
        return core, notes

    data = {}
    if isinstance(pm1, dict):
        result_obj = pm1.get("result")
        if isinstance(result_obj, dict):
            data = result_obj
        else:
            raw = pm1.get("output_text", "") or ""
            data = _extract_pm1_payload(raw)

    core, notes = _normalize_core_fields(
        data, title_fallback=str(context.get("initial", {}).get("title") or "")
    )
    articles_in = core["articles_in"] if isinstance(core["articles_in"], list) else []
    cards_in = core["cards_in"] if isinstance(core["cards_in"], list) else []

    dedup = {}
    for a in articles_in:
        if not isinstance(a, dict):
            continue
        pmid = str(a.get("pmid", "") or a.get("id", "") or "").strip()
        if not pmid:
            continue
        title = str(a.get("title", "") or "").strip()
        abstract = str(a.get("abstract", "") or "").strip()
        score = (2 if abstract else 0) + (1 if title else 0)
        pubdate = str(a.get("pubdate", "") or "")
        score += min(len(pubdate), 10) * 0.01
        prev = dedup.get(pmid)
        if prev is None or score > prev.get("_score", 0):
            item = dict(a)
            item["pmid"] = pmid
            item["_score"] = score
            dedup[pmid] = item
    articles = list(dedup.values())
    articles.sort(
        key=lambda x: (str(x.get("pubdate", "")), str(x.get("pmid", ""))), reverse=True
    )
    for a in articles:
        a.pop("_score", None)

    card_by_pmid = {}
    for c in cards_in:
        if not isinstance(c, dict):
            continue
        pmid = str(c.get("pmid", "") or c.get("id", "") or "").strip()
        if pmid and pmid not in card_by_pmid:
            card = dict(c)
            card["pmid"] = pmid
            card_by_pmid[pmid] = card

    evidence_cards = []
    for a in articles:
        pmid = str(a.get("pmid", "") or "").strip()
        c = card_by_pmid.get(pmid, {})
        if not c:
            c = {
                "pmid": pmid,
                "topic_bucket": a.get("topic_bucket", "general"),
                "inclusion_reason": "Selected for clinical relevance and recency.",
                "confidence": "medium",
                "title": a.get("title", ""),
                "pubdate": a.get("pubdate", ""),
                "source": a.get("source", ""),
            }
        evidence_cards.append(c)

    lines = []
    links_html_lines = []
    for i, a in enumerate(articles):
        pmid = str(a.get("pmid", "") or "").strip()
        title = str(a.get("title", "") or "").strip() or "(untitled)"
        abstract = str(a.get("abstract", "") or "").strip()
        line = "[" + str(i + 1) + "] " + title
        line += "\\n   PMID: " + (pmid or "n/a")
        if abstract:
            line += "\\n   Abstract: " + abstract[:3000]
        lines.append(line)
        pubmed_url = str(a.get("pubmed_url", "") or "").strip() or (
            "https://pubmed.ncbi.nlm.nih.gov/" + pmid + "/" if pmid else ""
        )
        link_parts = []
        if pubmed_url:
            link_parts.append('<a href="' + pubmed_url + '" target="_blank" rel="noopener noreferrer">PubMed</a>')
        links = " | ".join(link_parts) if link_parts else "No link"
        links_html_lines.append(
            "<li><strong>" + title + "</strong> (PMID: " + (pmid or "n/a") + ") — " + links + "</li>"
        )

    source_links_html = (
        "<ul>" + "".join(links_html_lines) + "</ul>"
        if links_html_lines
        else "<p>No sources to display.</p>"
    )
    article_pmids = [str(a.get("pmid") or "") for a in articles if str(a.get("pmid") or "").strip()]
    total_with_abstract = sum(1 for a in articles if str(a.get("abstract") or "").strip())
    per_domain_counts = {}
    for card in evidence_cards:
        if not isinstance(card, dict):
            continue
        bucket = str(card.get("topic_bucket") or "general").strip() or "general"
        per_domain_counts[bucket] = int(per_domain_counts.get(bucket, 0) or 0) + 1
    tier_distribution = {}
    for card in evidence_cards:
        if not isinstance(card, dict):
            continue
        tier = str(card.get("evidence_tier") or card.get("tier") or "unknown").strip() or "unknown"
        tier_distribution[tier] = int(tier_distribution.get(tier, 0) or 0) + 1

    def _year(v):
        s = str(v or "")
        digits = "".join(ch for ch in s if ch.isdigit())
        if len(digits) >= 4:
            y = int(digits[:4])
            if 1900 <= y <= 2100:
                return y
        return None

    years = [y for y in (_year(a.get("pubdate")) for a in articles) if y is not None]
    max_year = max(years) if years else None
    recency_counts = {"last_5y": 0, "last_10y": 0, "older": 0, "unknown": 0}
    for a in articles:
        y = _year(a.get("pubdate"))
        if y is None or max_year is None:
            recency_counts["unknown"] += 1
            continue
        delta = max_year - y
        if delta <= 5:
            recency_counts["last_5y"] += 1
        elif delta <= 10:
            recency_counts["last_10y"] += 1
        else:
            recency_counts["older"] += 1

    diagnostics_n = int(per_domain_counts.get("diagnostics", 0) or 0)
    treatment_n = int(per_domain_counts.get("treatment", 0) or 0)
    followup_n = int(per_domain_counts.get("follow_up", 0) or per_domain_counts.get("followup", 0) or 0)
    has_core_buckets = diagnostics_n > 0 and treatment_n > 0 and followup_n > 0
    retrieval_ok = len(articles) > 0
    missing_domains = []
    if diagnostics_n == 0:
        missing_domains.append("diagnostics")
    if treatment_n == 0:
        missing_domains.append("treatment")
    if followup_n == 0:
        missing_domains.append("follow_up")
    warnings = []
    if not retrieval_ok:
        warnings.append("No articles retrieved from PubMed retrieval pipeline.")
    if missing_domains:
        warnings.append("Missing core clinical domains: " + ", ".join(missing_domains))
    if bool(core["fallback_used"]):
        warnings.append("Browser fallback was used; verify core claims against PubMed links.")
    source_confidence = "high"
    if not retrieval_ok:
        source_confidence = "low"
    elif bool(core["fallback_used"]) or len(missing_domains) > 0:
        source_confidence = "medium"

    evidence_manifest = core["evidence_manifest"] if isinstance(core["evidence_manifest"], dict) else {}
    if not evidence_manifest:
        evidence_manifest = {
            "retrieval_channel": core["retrieval_channel"],
            "fallback_reason": core["fallback_reason"],
            "request_count": core["request_count"],
            "http_status_stats": core["http_status_stats"] if isinstance(core["http_status_stats"], dict) else {},
            "per_domain_pmid_counts": per_domain_counts,
            "tier_distribution": tier_distribution,
            "recency_distribution": recency_counts,
            "unique_pmid_count": len(set(article_pmids)),
            "total_requested": core["total_requested"] or len(articles_in),
            "total_analyzed": core["total_analyzed"] or len(articles),
        }
    return {
        "query_text": core["query_text"],
        "query_variants": core["query_variants"] if isinstance(core["query_variants"], list) else [],
        "fallback_used": core["fallback_used"],
        "retrieval_channel": core["retrieval_channel"],
        "fallback_reason": core["fallback_reason"],
        "total_found_estimate": core["total_found_estimate"],
        "total_requested": core["total_requested"] or len(articles_in),
        "total_analyzed": core["total_analyzed"] or len(articles),
        "total_with_abstract": core["total_with_abstract"] or total_with_abstract,
        "request_count": core["request_count"],
        "http_status_stats": core["http_status_stats"] if isinstance(core["http_status_stats"], dict) else {},
        "article_count": len(articles),
        "articles": articles,
        "article_pmids": article_pmids,
        "evidence_cards": evidence_cards,
        "articles_text": "\\n\\n".join(lines),
        "source_links_html": source_links_html,
        "retrieval_ok": retrieval_ok,
        "has_core_buckets": has_core_buckets,
        "per_domain_pmid_counts": per_domain_counts,
        "tier_distribution": tier_distribution,
        "recency_distribution": recency_counts,
        "unique_pmid_count": len(set(article_pmids)),
        "missing_domains": missing_domains,
        "warnings": warnings,
        "source_confidence": source_confidence,
        "evidence_manifest": evidence_manifest,
        "contract_mismatch_detected": bool(notes),
        "normalization_notes": notes,
    }
"""

    section_schema = json.dumps(
        {
            "fields": [
                {"name": "section_html", "type": "string", "required": True},
            ]
        },
        ensure_ascii=False,
    )
    overview_schema = json.dumps(
        {
            "fields": [
                {"name": "disease_name", "type": "string", "required": True},
                {"name": "section_html", "type": "string", "required": True},
                {"name": "key_updates", "type": "string", "required": True},
            ]
        },
        ensure_ascii=False,
    )
    references_schema = json.dumps(
        {
            "fields": [
                {"name": "section_html", "type": "string", "required": True},
                {"name": "references", "type": "string", "required": True},
                {"name": "disclaimer_html", "type": "string", "required": True},
            ]
        },
        ensure_ascii=False,
    )
    pass1_schema = json.dumps(
        {
            "fields": [
                {"name": "key_findings", "type": "string", "required": True},
                {"name": "strength_of_evidence", "type": "string", "required": True},
                {"name": "contradictions", "type": "string", "required": True},
                {"name": "evidence_gaps", "type": "string", "required": True},
                {"name": "key_pmids_cited", "type": "string", "required": True},
                {"name": "article_count_processed", "type": "integer", "required": True},
            ]
        },
        ensure_ascii=False,
    )
    rubric_schema = json.dumps(
        {
            "fields": [
                {"name": "coverage_score", "type": "integer", "required": True},
                {"name": "completeness_score", "type": "integer", "required": True},
                {"name": "citation_density_score", "type": "integer", "required": True},
                {"name": "contradiction_handling_score", "type": "integer", "required": True},
                {"name": "weak_sections", "type": "string", "required": True},
                {"name": "retry_reasons", "type": "string", "required": True},
                {"name": "summary", "type": "string", "required": True},
            ]
        },
        ensure_ascii=False,
    )
    pm_fix_output_schema = json.dumps(
        {
            "fields": [
                {"name": "disease_name", "type": "string", "required": True},
                {"name": "guideline_html", "type": "string", "required": True},
                {"name": "diagnostic_algorithm_html", "type": "string", "required": True},
                {"name": "treatment_steps_html", "type": "string", "required": True},
                {"name": "monitoring_protocol_html", "type": "string", "required": True},
                {"name": "recommendation_matrix_html", "type": "string", "required": True},
                {"name": "red_flags_html", "type": "string", "required": True},
                {"name": "contraindications_html", "type": "string", "required": True},
                {"name": "follow_up_schedule_html", "type": "string", "required": True},
                {"name": "evidence_gaps_html", "type": "string", "required": True},
                {"name": "disclaimer_html", "type": "string", "required": True},
                {"name": "key_updates", "type": "string", "required": True},
                {"name": "confidence_level", "type": "string", "required": True},
                {"name": "evidence_score", "type": "integer", "required": True},
                {"name": "confidence_index", "type": "integer", "required": True},
                {"name": "reliability_assessment_html", "type": "string", "required": True},
                {"name": "source_links_html", "type": "string", "required": True},
                {"name": "references", "type": "string", "required": True},
                {"name": "article_count", "type": "integer", "required": True},
            ]
        },
        ensure_ascii=False,
    )
    pm_eval_issue_prompt = (
        "Issue codes (examples — add a clear code when none fit): INTERNAL_CONTRADICTION, "
        "CROSS_SECTION_NUMERIC_MISMATCH, PMID_OR_SOURCE_MISMATCH, NUMERIC_OR_COUNT_MISMATCH, "
        "SECTION_LEVEL_MISMATCH, IMPOSSIBLE_OR_FAKE_PMID, META_AGENT_TEXT_LEAK, "
        "UNSUPPORTED_SCREENING_OR_DOSE_CLAIM.\n\n"
        "Emphasis:\n"
        "- Compare the same drug, trial primary endpoint, dosing schedule, epidemiology figures, "
        "and radiation vs contraindication statements across every heading in SYNTHESIS; each "
        "material clash is at least one issue with both locations.\n"
        "- Flag PMIDs with implausible digit counts vs realistic PubMed ranges.\n"
        "- Flag any visible assistant planning/meta prose.\n"
        "- suggested_fix must be one concrete harmonization per issue (single evidence-aligned "
        "reading from REFERENCE_FACTS, or explicit downgrade to conditional/unknown when refs "
        "are insufficient)."
    )
    pm_eval_source_nodes_json = _PUBMED_EVAL_SOURCE_NODES_JSON
    pm_fix_prompt = (
        "You are revising the assembled clinical guideline from pm-4-build (after PMID scrub/repair). "
        "Return the same structured fields as pm-4-build.\n\n"
        "--- Evaluator (pm_eval) ---\n"
        "issues_found: {{ context.pm_eval.issues_found }}\n"
        "quality_summary: {{ context.pm_eval.quality_summary }}\n"
        "issues: {{ context.pm_eval.issues }}\n"
        "correction_instructions:\n"
        "{{ context.pm_eval.correction_instructions }}\n\n"
        "Rules:\n"
        "1. Apply correction_instructions and every issue suggested_fix across ALL HTML fields "
        "so the document is internally consistent.\n"
        "2. Remove assistant/meta/planning language if flagged.\n"
        "3. Do not invent clinical facts beyond the evidence corpus; remove or qualify "
        "unsupported PMIDs.\n"
        "4. If issues_found is false or issues is empty, keep pm-4-build content except "
        "trivial typo fixes.\n"
        "5. Use professional clinical English; valid HTML only.\n\n"
        "Evidence corpus:\n"
        "Disease/topic: {{ context.pm-2.result.query_text }}\n"
        "Total analyzed: {{ context.pm-2.result.total_analyzed }}\n"
        "Browser fallback used: {{ context.pm-2.result.fallback_used }}\n"
        "Evidence appraisal: score {{ context.pm-3.evidence_score }}, level "
        "{{ context.pm-3.evidence_level }}, confidence_index {{ context.pm-3.confidence_index }}\n\n"
        "--- Articles ---\n"
        "{{ context.pm-2.result.articles_text }}\n\n"
        "--- Baseline (pm-4-build) ---\n"
        "disease_name: {{ context.pm-4-build.disease_name }}\n"
        "article_count: {{ context.pm-4-build.article_count }}\n"
        "evidence_score: {{ context.pm-4-build.evidence_score }}\n"
        "confidence_index: {{ context.pm-4-build.confidence_index }}\n"
        "confidence_level: {{ context.pm-4-build.confidence_level }}\n"
        "key_updates: {{ context.pm-4-build.key_updates }}\n"
        "guideline_html:\n{{ context.pm-4-build.guideline_html }}\n"
        "diagnostic_algorithm_html:\n{{ context.pm-4-build.diagnostic_algorithm_html }}\n"
        "treatment_steps_html:\n{{ context.pm-4-build.treatment_steps_html }}\n"
        "monitoring_protocol_html:\n{{ context.pm-4-build.monitoring_protocol_html }}\n"
        "recommendation_matrix_html:\n{{ context.pm-4-build.recommendation_matrix_html }}\n"
        "red_flags_html:\n{{ context.pm-4-build.red_flags_html }}\n"
        "contraindications_html:\n{{ context.pm-4-build.contraindications_html }}\n"
        "follow_up_schedule_html:\n{{ context.pm-4-build.follow_up_schedule_html }}\n"
        "evidence_gaps_html:\n{{ context.pm-4-build.evidence_gaps_html }}\n"
        "disclaimer_html:\n{{ context.pm-4-build.disclaimer_html }}\n"
        "reliability_assessment_html:\n{{ context.pm-4-build.reliability_assessment_html }}\n"
        "source_links_html:\n{{ context.pm-4-build.source_links_html }}\n"
        "references:\n{{ context.pm-4-build.references }}\n\n"
        "Produce the corrected structured output per schema."
    )

    pubmed_nodes = [
        {
            "node_id": "start",
            "node_type": "trigger",
            "label": "PubMed Search Input",
            "description": "Accepts a disease or medical topic from the ticket title/description.",
            "prompt": "Entry point: take the disease/topic from ticket title and description, pass to agentic retrieval.",
            "position_x": 0,
            "position_y": 0,
            "prompt_mode": "agentic",
            "output_schema": None,
            "python_source": None,
        },
        {
            "node_id": "pm-1",
            "node_type": "prompt",
            "label": "Agentic PubMed Retrieval",
            "description": "AI agent iteratively searches PubMed tools and can use browser fallback if recall is low.",
            "prompt": "You are responsible for collecting high-quality clinical evidence from PubMed.\n\nGoal: return a strict JSON object only, with this shape:\n{\n  \"query_text\": \"...\",\n  \"query_variants\": [\"...\"],\n  \"fallback_used\": true/false,\n  \"total_found_estimate\": 0,\n  \"articles\": [\n    {\n      \"pmid\": \"...\",\n      \"title\": \"...\",\n      \"authors\": \"...\",\n      \"source\": \"...\",\n      \"pubdate\": \"...\",\n      \"doi\": \"...\",\n      \"abstract\": \"...\",\n      \"pubmed_url\": \"...\",\n      \"doi_url\": \"...\",\n      \"topic_bucket\": \"pathogenesis|diagnostics|treatment|follow_up|general\"\n    }\n  ],\n  \"evidence_cards\": [\n    {\n      \"pmid\": \"...\",\n      \"topic_bucket\": \"...\",\n      \"inclusion_reason\": \"...\",\n      \"confidence\": \"high|medium|low\",\n      \"title\": \"...\",\n      \"pubdate\": \"...\",\n      \"source\": \"...\"\n    }\n  ]\n}\n\nMandatory process:\n1) Build 3-6 PubMed query variants for the topic.\n2) Call pubmed_search_articles with max_analyze large enough to cover all found PMIDs.\n3) Call pubmed_fetch_article_details ONCE for all retrieved PMIDs (batching is allowed, dropping records is not).\n4) Use pubmed_browser_search only when API path clearly fails or returns zero/near-zero useful records.\n5) Keep all clinically relevant PMIDs in output; do not reduce to top-N sample.\n6) Keep output compact to avoid context overflow (use concise metadata and abstract snippets only).\n7) Do NOT call update_ticket_status in this step.\n8) Return only JSON, no markdown.\n\nTicket context:\n- Title: {{ context.initial.title }}\n- Description: {{ context.initial.description }}",
            "position_x": 0,
            "position_y": 160,
            "prompt_mode": "agentic",
            "output_schema": None,
            "python_source": None,
        },
        {
            "node_id": "pm-2",
            "node_type": "code",
            "label": "Normalize and Rank Evidence",
            "description": "Parses agent output, normalizes evidence cards and builds deterministic source links.",
            "prompt": "",
            "position_x": 0,
            "position_y": 340,
            "prompt_mode": "agentic",
            "output_schema": None,
            "python_source": pm2_source,
        },
        {
            "node_id": "pm-3",
            "node_type": "prompt",
            "label": "Evidence Quality Scoring",
            "description": "LLM estimates reliability and evidence strength of the fetched PubMed set.",
            "prompt": "You are an evidence appraisal assistant.\n\nBased ONLY on the evidence cards and metadata below, estimate credibility of the evidence base for clinical decision support.\n\nDisease/topic: {{ context.pm-2.result.query_text }}\nArticles retrieved: {{ context.pm-2.result.article_count }}\nBrowser fallback used: {{ context.pm-2.result.fallback_used }}\n\n--- Evidence cards ---\n{{ context.pm-2.result.evidence_cards }}\n\n--- Articles ---\n{{ context.pm-2.result.articles_text }}\n\nReturn structured assessment:\n1. evidence_score (0-100)\n2. evidence_level: high/moderate/low/very_low\n3. confidence_index (0-100)\n4. risk_of_bias\n5. main_limitations\n6. consistency_assessment\n7. clinical_reliability_comment\n\nDo not invent study details not present in the input.",
            "position_x": 0,
            "position_y": 520,
            "prompt_mode": "simple",
            "output_schema": '{"fields":[{"name":"evidence_score","type":"integer","required":true},{"name":"evidence_level","type":"string","required":true},{"name":"confidence_index","type":"integer","required":true},{"name":"risk_of_bias","type":"string","required":true},{"name":"main_limitations","type":"string","required":true},{"name":"consistency_assessment","type":"string","required":true},{"name":"clinical_reliability_comment","type":"string","required":true}]}',
            "python_source": None,
        },
        {
            "node_id": "pass1-overview",
            "node_type": "prompt",
            "label": "Pass1: Overview Evidence Synthesis",
            "description": "Synthesize evidence facts for overview before drafting.",
            "prompt": "Pass 1 (Evidence Synthesis). Use ONLY the provided corpus.\n\nTopic: {{ context.pm-2.result.query_text }}\nCorpus:\n{{ context.pm-2.result.articles_text }}\n\nProduce structured synthesis for OVERVIEW with evidence strength, contradictions, explicit gaps, and canonical PMID list.",
            "position_x": -900,
            "position_y": 660,
            "prompt_mode": "simple",
            "output_schema": pass1_schema,
            "python_source": None,
        },
        {
            "node_id": "pass1-epidemiology",
            "node_type": "prompt",
            "label": "Pass1: Epidemiology Evidence Synthesis",
            "description": "Synthesize epidemiology evidence before drafting.",
            "prompt": "Pass 1 (Evidence Synthesis) for EPIDEMIOLOGY.\nUse ONLY:\n{{ context.pm-2.result.articles_text }}\nReturn structured findings, strength, contradictions, gaps, PMIDs.",
            "position_x": -650,
            "position_y": 660,
            "prompt_mode": "simple",
            "output_schema": pass1_schema,
            "python_source": None,
        },
        {
            "node_id": "pass1-pathogenesis",
            "node_type": "prompt",
            "label": "Pass1: Pathogenesis Evidence Synthesis",
            "description": "Synthesize pathogenesis evidence before drafting.",
            "prompt": "Pass 1 (Evidence Synthesis) for PATHOGENESIS/RISK FACTORS.\nUse ONLY:\n{{ context.pm-2.result.articles_text }}\nReturn structured findings, strength, contradictions, gaps, PMIDs.",
            "position_x": -400,
            "position_y": 660,
            "prompt_mode": "simple",
            "output_schema": pass1_schema,
            "python_source": None,
        },
        {
            "node_id": "pass1-diagnostics",
            "node_type": "prompt",
            "label": "Pass1: Diagnostics Evidence Synthesis",
            "description": "Synthesize diagnostics evidence before drafting.",
            "prompt": "Pass 1 (Evidence Synthesis) for DIAGNOSTICS.\nUse ONLY:\n{{ context.pm-2.result.articles_text }}\nReturn structured findings, strength, contradictions, gaps, PMIDs.",
            "position_x": -150,
            "position_y": 660,
            "prompt_mode": "simple",
            "output_schema": pass1_schema,
            "python_source": None,
        },
        {
            "node_id": "pass1-treatment",
            "node_type": "prompt",
            "label": "Pass1: Treatment Evidence Synthesis",
            "description": "Synthesize treatment evidence before drafting.",
            "prompt": "Pass 1 (Evidence Synthesis) for TREATMENT.\nUse ONLY:\n{{ context.pm-2.result.articles_text }}\nReturn structured findings, strength, contradictions, gaps, PMIDs.",
            "position_x": 350,
            "position_y": 660,
            "prompt_mode": "simple",
            "output_schema": pass1_schema,
            "python_source": None,
        },
        {
            "node_id": "pass1-monitoring",
            "node_type": "prompt",
            "label": "Pass1: Monitoring Evidence Synthesis",
            "description": "Synthesize monitoring evidence before drafting.",
            "prompt": "Pass 1 (Evidence Synthesis) for MONITORING.\nUse ONLY:\n{{ context.pm-2.result.articles_text }}\nReturn structured findings, strength, contradictions, gaps, PMIDs.",
            "position_x": 600,
            "position_y": 660,
            "prompt_mode": "simple",
            "output_schema": pass1_schema,
            "python_source": None,
        },
        {
            "node_id": "pass1-followup",
            "node_type": "prompt",
            "label": "Pass1: Follow-up Evidence Synthesis",
            "description": "Synthesize follow-up/prognosis evidence before drafting.",
            "prompt": "Pass 1 (Evidence Synthesis) for FOLLOW-UP/PROGNOSIS.\nUse ONLY:\n{{ context.pm-2.result.articles_text }}\nReturn structured findings, strength, contradictions, gaps, PMIDs.",
            "position_x": 850,
            "position_y": 660,
            "prompt_mode": "simple",
            "output_schema": pass1_schema,
            "python_source": None,
        },
        {
            "node_id": "pm-4-overview",
            "node_type": "prompt",
            "label": "Guideline: Overview",
            "description": "High-level overview and key updates based on normalized evidence.",
            "prompt": "=== VERIFIED PMID REFERENCE TABLE ===\n{{ context.pm-1.result.pmid_reference_table }}\n=====================================\n\nCITATION RULE: Cite ONLY PMIDs listed in the table above. Never invent PMIDs.\nIf claim has no matching PMID → write [evidence needed]. PMIDs must be 7-9 digits (1,000,000 – 41,500,000).\n\nPass 2 (Clinical Drafting) for OVERVIEW.\nUse ONLY pass1 synthesis:\n{{ context.pass1-overview }}\n\nWrite comprehensive clinician-grade HTML with inline PMID citations for each claim.\n\n{{ context.pm-rag.result.consensus_context }}",
            "position_x": -900,
            "position_y": 760,
            "prompt_mode": "simple",
            "output_schema": overview_schema,
            "python_source": None,
        },
        {
            "node_id": "pm-4-epidemiology",
            "node_type": "prompt",
            "label": "Guideline: Epidemiology",
            "description": "Epidemiology and burden section.",
            "prompt": "=== VERIFIED PMID REFERENCE TABLE ===\n{{ context.pm-1.result.pmid_reference_table }}\n=====================================\n\nCITATION RULE: Cite ONLY PMIDs listed in the table above. Never invent PMIDs.\nIf claim has no matching PMID → write [evidence needed]. PMIDs must be 7-9 digits (1,000,000 – 41,500,000).\n\nPass 2 (Clinical Drafting) for EPIDEMIOLOGY.\nUse ONLY pass1 synthesis:\n{{ context.pass1-epidemiology }}\n\nProvide detailed clinician-grade epidemiology section with inline PMID citations and explicit Evidence gap labels.",
            "position_x": -650,
            "position_y": 760,
            "prompt_mode": "simple",
            "output_schema": section_schema,
            "python_source": None,
        },
        {
            "node_id": "pm-4-pathogenesis",
            "node_type": "prompt",
            "label": "Guideline: Pathogenesis",
            "description": "Pathogenesis and mechanism section.",
            "prompt": "=== VERIFIED PMID REFERENCE TABLE ===\n{{ context.pm-1.result.pmid_reference_table }}\n=====================================\n\nCITATION RULE: Cite ONLY PMIDs listed in the table above. Never invent PMIDs.\nIf claim has no matching PMID → write [evidence needed]. PMIDs must be 7-9 digits (1,000,000 – 41,500,000).\n\nPass 2 (Clinical Drafting) for PATHOGENESIS/RISK FACTORS.\nUse ONLY pass1 synthesis:\n{{ context.pass1-pathogenesis }}\n\nProduce detailed clinician-grade section with explicit certainty labels and inline PMID citations.\n\n{{ context.pm-rag.result.consensus_context }}",
            "position_x": -400,
            "position_y": 760,
            "prompt_mode": "simple",
            "output_schema": section_schema,
            "python_source": None,
        },
        {
            "node_id": "pm-4-diagnostics",
            "node_type": "prompt",
            "label": "Guideline: Diagnostics",
            "description": "Diagnostic pathway and differential diagnosis section.",
            "prompt": "=== VERIFIED PMID REFERENCE TABLE ===\n{{ context.pm-1.result.pmid_reference_table }}\n=====================================\n\nCITATION RULE: Cite ONLY PMIDs listed in the table above. Never invent PMIDs.\nIf claim has no matching PMID → write [evidence needed]. PMIDs must be 7-9 digits (1,000,000 – 41,500,000).\n\nPass 2 (Clinical Drafting) for DIAGNOSTICS.\nUse ONLY pass1 synthesis:\n{{ context.pass1-diagnostics }}\n\nProduce highly detailed diagnostic workflow (presentation, imaging, labs, biopsy criteria, differential diagnosis) with inline PMID citations.\n\n{{ context.pm-rag.result.consensus_context }}",
            "position_x": -150,
            "position_y": 760,
            "prompt_mode": "simple",
            "output_schema": section_schema,
            "python_source": None,
        },
        {
            "node_id": "pm-4-red-flags",
            "node_type": "prompt",
            "label": "Guideline: Red Flags & Contraindications",
            "description": "Critical warning signs and contraindications.",
            "prompt": "=== VERIFIED PMID REFERENCE TABLE ===\n{{ context.pm-1.result.pmid_reference_table }}\n=====================================\n\nCITATION RULE: Cite ONLY PMIDs listed in the table above. Never invent PMIDs.\nIf claim has no matching PMID → write [evidence needed]. PMIDs must be 7-9 digits (1,000,000 – 41,500,000).\n\nYou are preparing the Red Flags & Contraindications section in English.\n\nContext:\n- Disease/topic: {{ context.pm-2.result.query_text }}\n\nEvidence corpus:\n{{ context.pm-2.result.articles_text }}\n\nTask:\nList urgent red flags, contraindications, and escalation triggers.\n\nEvidence policy:\n- Every red flag/contraindication must cite PMID(s).\n- If evidence is missing for a safety topic, explicitly write `Evidence gap:`.\n- Avoid absolute recommendations when certainty is low.\n\nOutput: `section_html` as valid clinical HTML.",
            "position_x": 100,
            "position_y": 760,
            "prompt_mode": "simple",
            "output_schema": section_schema,
            "python_source": None,
        },
        {
            "node_id": "pm-4-treatment",
            "node_type": "prompt",
            "label": "Guideline: Treatment & Management",
            "description": "Treatment strategy and management section.",
            "prompt": "=== VERIFIED PMID REFERENCE TABLE ===\n{{ context.pm-1.result.pmid_reference_table }}\n=====================================\n\nCITATION RULE: Cite ONLY PMIDs listed in the table above. Never invent PMIDs.\nIf claim has no matching PMID → write [evidence needed]. PMIDs must be 7-9 digits (1,000,000 – 41,500,000).\n\nPass 2 (Clinical Drafting) for TREATMENT & MANAGEMENT.\nUse ONLY pass1 synthesis:\n{{ context.pass1-treatment }}\n\nBuild extensive clinician-grade treatment pathway (first/second line, contraindications, adverse-event monitoring, escalation) with inline PMID citations.\n\n{{ context.pm-rag.result.consensus_context }}",
            "position_x": 350,
            "position_y": 760,
            "prompt_mode": "simple",
            "output_schema": section_schema,
            "python_source": None,
        },
        {
            "node_id": "pm-4-monitoring",
            "node_type": "prompt",
            "label": "Guideline: Monitoring Protocol",
            "description": "Monitoring protocol section.",
            "prompt": "=== VERIFIED PMID REFERENCE TABLE ===\n{{ context.pm-1.result.pmid_reference_table }}\n=====================================\n\nCITATION RULE: Cite ONLY PMIDs listed in the table above. Never invent PMIDs.\nIf claim has no matching PMID → write [evidence needed]. PMIDs must be 7-9 digits (1,000,000 – 41,500,000).\n\nPass 2 (Clinical Drafting) for MONITORING.\nUse ONLY pass1 synthesis:\n{{ context.pass1-monitoring }}\n\nProduce detailed monitoring protocol (frequency, tests, AE checks, escalation thresholds) with inline PMID citations.",
            "position_x": 600,
            "position_y": 760,
            "prompt_mode": "simple",
            "output_schema": section_schema,
            "python_source": None,
        },
        {
            "node_id": "pm-4-followup",
            "node_type": "prompt",
            "label": "Guideline: Follow-Up & Prognosis",
            "description": "Follow-up schedule and outcomes section.",
            "prompt": "=== VERIFIED PMID REFERENCE TABLE ===\n{{ context.pm-1.result.pmid_reference_table }}\n=====================================\n\nCITATION RULE: Cite ONLY PMIDs listed in the table above. Never invent PMIDs.\nIf claim has no matching PMID → write [evidence needed]. PMIDs must be 7-9 digits (1,000,000 – 41,500,000).\n\nPass 2 (Clinical Drafting) for FOLLOW-UP & PROGNOSIS.\nUse ONLY pass1 synthesis:\n{{ context.pass1-followup }}\n\nDeliver detailed long-term follow-up and prognosis section with risk-stratified recommendations and inline PMID citations.",
            "position_x": 850,
            "position_y": 760,
            "prompt_mode": "simple",
            "output_schema": section_schema,
            "python_source": None,
        },
        {
            "node_id": "pm-4-references",
            "node_type": "prompt",
            "label": "Guideline: References & Gaps",
            "description": "References list, evidence gaps and medical disclaimer.",
            "prompt": "You are preparing the References, Evidence Gaps, and Patient Communication section in English.\n\nContext:\n- Disease/topic: {{ context.pm-2.result.query_text }}\n- Source links html: {{ context.pm-2.result.source_links_html }}\n\nEvidence corpus:\n{{ context.pm-2.result.articles_text }}\n\nTask:\nReturn:\n1) `section_html`: concise references overview + explicit evidence gaps + patient communication key points.\n2) `references`: plain-text reference list with inline PMID for each cited paper.\n3) `disclaimer_html`: strict medical disclaimer emphasizing evidence limitations and clinician judgment.\n\nEvidence policy:\n- Do not cite studies not present in corpus.\n- Mark unresolved clinical questions as `Evidence gap:`.",
            "position_x": 1100,
            "position_y": 760,
            "prompt_mode": "simple",
            "output_schema": references_schema,
            "python_source": None,
        },
        {
            "node_id": "pm-merge",
            "node_type": "code",
            "label": "Merge evidence domains",
            "description": "Merge domain synthesis outputs and collect PMIDs.",
            "prompt": "",
            "position_x": 250,
            "position_y": 960,
            "prompt_mode": "agentic",
            "output_schema": None,
            "python_source": PM_MERGE_SOURCE,
        },
        {
            "node_id": "pm-4-build",
            "node_type": "code",
            "label": "Build Final Guideline",
            "description": "Assemble full guideline payload from section nodes.",
            "prompt": "",
            "position_x": 550,
            "position_y": 1140,
            "prompt_mode": "agentic",
            "output_schema": None,
            "python_source": PM4_BUILD_SOURCE,
        },
        {
            "node_id": "pm_gate",
            "node_type": "code",
            "label": "PubMed quality gate",
            "description": "Quality gate for normalized retrieval output.",
            "prompt": "",
            "position_x": -250,
            "position_y": 520,
            "prompt_mode": "agentic",
            "output_schema": None,
            "python_source": PM_GATE_SOURCE,
        },
        {
            "node_id": "pm-5",
            "node_type": "code",
            "label": "Grounding validation",
            "description": "Validate citation grounding and transparency.",
            "prompt": "",
            "position_x": 800,
            "position_y": 1320,
            "prompt_mode": "agentic",
            "output_schema": None,
            "python_source": PM5_SOURCE,
        },
        {
            "node_id": "pm-5-scrub",
            "node_type": "pmid_scrub",
            "label": "PMID Scrubber",
            "description": "Deterministically removes hallucinated PMIDs from synthesis output.",
            "prompt": "",
            "position_x": 800,
            "position_y": 1410,
            "prompt_mode": "agentic",
            "output_schema": None,
            "python_source": None,
        },
        {
            "node_id": "pm-rubric",
            "node_type": "prompt",
            "label": "Quality Rubric Scoring",
            "description": "Score section quality and identify weak sections for targeted retry.",
            "prompt": "Assess section quality with a strict clinical rubric. Score all dimensions in 0-100:\n- coverage_score\n- completeness_score\n- citation_density_score\n- contradiction_handling_score\n\nInput sections:\nOVERVIEW={{ context.pm-4-overview.section_html }}\nEPIDEMIOLOGY={{ context.pm-4-epidemiology.section_html }}\nPATHOGENESIS={{ context.pm-4-pathogenesis.section_html }}\nDIAGNOSTICS={{ context.pm-4-diagnostics.section_html }}\nTREATMENT={{ context.pm-4-treatment.section_html }}\nMONITORING={{ context.pm-4-monitoring.section_html }}\nFOLLOWUP={{ context.pm-4-followup.section_html }}\n\nRules:\n- If any section lacks clear inline PMID support for factual claims, include its node_id in weak_sections.\n- If any clinically expected subtopic is absent, include node_id in weak_sections.\n- weak_sections must be comma-separated node_ids.\n- retry_reasons must map node_id->brief reason in one string.\n- summary must explain global quality and readiness.",
            "position_x": 300,
            "position_y": 980,
            "prompt_mode": "simple",
            "output_schema": rubric_schema,
            "python_source": None,
        },
        {
            "node_id": "pm-targeted-retry",
            "node_type": "code",
            "label": "Targeted Retry Planner",
            "description": "Plans weak sections for optional retry waves.",
            "prompt": "",
            "position_x": 420,
            "position_y": 1060,
            "prompt_mode": "agentic",
            "output_schema": None,
            "python_source": "def run(context):\n    outs = context.get('outputs', {})\n    rub = outs.get('pm-rubric', {})\n    if isinstance(rub, dict) and 'result' in rub and isinstance(rub['result'], dict):\n        rub = rub['result']\n    weak = str(rub.get('weak_sections') or '').strip()\n    planned = [w.strip() for w in weak.split(',') if w.strip()]\n    max_retry_waves = 2\n    return {\n        'weak_sections': planned,\n        'planned_retry_count': len(planned),\n        'max_retry_waves': max_retry_waves,\n        'retry_reasons': str(rub.get('retry_reasons') or ''),\n        'retry_performed': False,\n        'retry_blocker': 'flow_is_dag_no_runtime_loop' if planned else '',\n    }\n",
        },
        {
            "node_id": "pm-rag",
            "node_type": "guidelines_rag",
            "label": "Guidelines RAG",
            "description": "Fetch consensus anchor abstracts for RAG grounding.",
            "prompt": "",
            "position_x": 200,
            "position_y": 260,
            "prompt_mode": "agentic",
            "output_schema": None,
            "python_source": None,
        },
        {
            "node_id": "pm-5-repair",
            "node_type": "prompt",
            "label": "PMID Repair Pass",
            "description": "Replaces [PMID UNVERIFIED] markers with best-match PMIDs from the reference table.",
            "prompt": "=== VERIFIED PMID REFERENCE TABLE ===\n{{ context.pm-1.result.pmid_reference_table }}\n=====================================\n\n=== DOCUMENT WITH UNVERIFIED MARKERS ===\n{{ context.pm-5-scrub.cleaned_text }}\n=====================================\n\nYou are a medical evidence editor. For each [PMID UNVERIFIED] marker:\n1. Look at the surrounding claim.\n2. Find the best matching PMID from the reference table above.\n3. If match found → replace [PMID UNVERIFIED] with the correct PMID citation.\n4. If no match → remove the citation marker, keep the claim if it is clinically well-established, otherwise remove the claim too.\n5. Do NOT add any PMIDs not in the reference table.\n6. Preserve all HTML formatting.\n7. Return JSON with key \"output_text\" containing the complete repaired document.",
            "position_x": 800,
            "position_y": 1460,
            "prompt_mode": "simple",
            "output_schema": '{"fields":[{"name":"output_text","type":"string","required":true}]}',
            "python_source": None,
        },
        {
            "node_id": "pm-verify",
            "node_type": "pmid_verify",
            "label": "PMID Verification",
            "description": "Extract and verify PMIDs cited in synthesis output.",
            "prompt": "",
            "position_x": 1000,
            "position_y": 1550,
            "prompt_mode": "agentic",
            "output_schema": None,
            "python_source": None,
        },
        {
            "node_id": "pm_eval",
            "node_type": "evaluation_check",
            "label": "Consistency evaluation",
            "description": "Final pass: flag cross-section inconsistencies vs retrieval facts (does not rewrite HTML).",
            "prompt": pm_eval_issue_prompt,
            "position_x": 1000,
            "position_y": 1640,
            "prompt_mode": "simple",
            "output_schema": None,
            "python_source": None,
            "evaluation_source_nodes_json": pm_eval_source_nodes_json,
        },
        {
            "node_id": "pm_fix",
            "node_type": "prompt",
            "label": "Guideline consistency repair",
            "description": "Applies pm_eval feedback to the assembled guideline (pm-4-build schema).",
            "prompt": pm_fix_prompt,
            "position_x": 1000,
            "position_y": 1730,
            "prompt_mode": "simple",
            "output_schema": pm_fix_output_schema,
            "python_source": None,
        },
        {
            "node_id": "end",
            "node_type": "end",
            "label": "End",
            "description": "Flow completed — literature review ready.",
            "prompt": "",
            "position_x": 1000,
            "position_y": 1820,
            "prompt_mode": "agentic",
            "output_schema": None,
            "python_source": None,
        },
    ]
    _nodes_with_disease_prompt = {
        "pm-1",
        "pm-3",
        "pass1-overview",
        "pm-4-overview",
        "pm-4-diagnostics",
        "pm-4-treatment",
        "pm-4-red-flags",
        "pm-4-monitoring",
    }
    for node in pubmed_nodes:
        nid = node.get("node_id")
        if nid in _nodes_with_disease_prompt and node.get("prompt"):
            node["prompt"] = append_disease_prompt_block(str(node["prompt"]))
    for node in pubmed_nodes:
        cur.execute("SELECT 1 FROM flow_definitions WHERE flow_key = 'pubmed' AND node_id = ? LIMIT 1", (node["node_id"],))
        exists = cur.fetchone() is not None
        params = (
            node["node_type"],
            node["label"],
            node["description"],
            node["prompt"],
            3,
            1,
            now,
            node["position_x"],
            node["position_y"],
            node["prompt_mode"],
            None,
            None,
            node["output_schema"],
            0,
            node["python_source"],
            None,
            None,
            None,
            None,
            "similar",
            None,
            node["node_id"],
        )
        if exists:
            cur.execute(
                """UPDATE flow_definitions
                   SET node_type = ?, label = ?, description = ?, prompt = ?, max_retry = ?, version = ?, updated_at = ?,
                       position_x = ?, position_y = ?, prompt_mode = ?, model_name = ?, output_schema_key = ?, output_schema = ?,
                       agentic_step_close = ?, python_source = ?, http_url = ?, http_method = ?, http_headers = ?, http_body = ?,
                       rag_operation = ?, rag_body_json = ?
                   WHERE flow_key = 'pubmed' AND node_id = ?""",
                params,
            )
        else:
            cur.execute(
                """INSERT INTO flow_definitions (
                    flow_key, node_id, node_type, label, description, prompt, loop_policy, execution_policy, max_retry, version, updated_at,
                    position_x, position_y, prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close, python_source,
                    http_url, http_method, http_headers, http_body, rag_operation, rag_body_json
                ) VALUES (?, ?, ?, ?, ?, ?, 'none', 'auto', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "pubmed",
                    node["node_id"],
                    node["node_type"],
                    node["label"],
                    node["description"],
                    node["prompt"],
                    3,
                    1,
                    now,
                    node["position_x"],
                    node["position_y"],
                    node["prompt_mode"],
                    None,
                    None,
                    node["output_schema"],
                    0,
                    node["python_source"],
                    None,
                    None,
                    None,
                    None,
                    "similar",
                    None,
                ),
            )
        eval_sources = node.get("evaluation_source_nodes_json")
        if eval_sources and node.get("node_id") == "pm_eval":
            cur.execute(
                """UPDATE flow_definitions SET evaluation_source_nodes_json = ?
                   WHERE flow_key = 'pubmed' AND node_id = 'pm_eval'""",
                (eval_sources,),
            )

    valid_node_ids = tuple(n["node_id"] for n in pubmed_nodes)
    placeholders = ",".join("?" for _ in valid_node_ids)
    cur.execute(
        f"DELETE FROM flow_definitions WHERE flow_key = 'pubmed' AND node_id NOT IN ({placeholders})",
        valid_node_ids,
    )

    cur.execute("DELETE FROM flow_edges WHERE flow_key = 'pubmed'")
    edges = [
        ("pubmed", "start", "pm-1"),
        ("pubmed", "pm-1", "pm-rag"),
        ("pubmed", "pm-rag", "pm-2"),
        ("pubmed", "pm-2", "pm_gate"),
        ("pubmed", "pm_gate", "pm-3"),
        ("pubmed", "pm-3", "pass1-overview"),
        ("pubmed", "pm-3", "pass1-epidemiology"),
        ("pubmed", "pm-3", "pass1-pathogenesis"),
        ("pubmed", "pm-3", "pass1-diagnostics"),
        ("pubmed", "pm-3", "pass1-treatment"),
        ("pubmed", "pm-3", "pass1-monitoring"),
        ("pubmed", "pm-3", "pass1-followup"),
        ("pubmed", "pass1-overview", "pm-4-overview"),
        ("pubmed", "pass1-epidemiology", "pm-4-epidemiology"),
        ("pubmed", "pass1-pathogenesis", "pm-4-pathogenesis"),
        ("pubmed", "pass1-diagnostics", "pm-4-diagnostics"),
        ("pubmed", "pass1-treatment", "pm-4-treatment"),
        ("pubmed", "pass1-monitoring", "pm-4-monitoring"),
        ("pubmed", "pass1-followup", "pm-4-followup"),
        ("pubmed", "pm-3", "pm-4-red-flags"),
        ("pubmed", "pm-3", "pm-4-references"),
        ("pubmed", "pm-4-overview", "pm-rubric"),
        ("pubmed", "pm-4-epidemiology", "pm-rubric"),
        ("pubmed", "pm-4-pathogenesis", "pm-rubric"),
        ("pubmed", "pm-4-diagnostics", "pm-rubric"),
        ("pubmed", "pm-4-red-flags", "pm-rubric"),
        ("pubmed", "pm-4-treatment", "pm-rubric"),
        ("pubmed", "pm-4-monitoring", "pm-rubric"),
        ("pubmed", "pm-4-followup", "pm-rubric"),
        ("pubmed", "pm-4-references", "pm-rubric"),
        ("pubmed", "pm-rubric", "pm-targeted-retry"),
        ("pubmed", "pm-targeted-retry", "pm-merge"),
        ("pubmed", "pm-rubric", "pm-merge"),
        ("pubmed", "pm-merge", "pm-4-build"),
        ("pubmed", "pm-4-build", "pm-5"),
        ("pubmed", "pm-5", "pm-5-scrub"),
        ("pubmed", "pm-5-scrub", "pm-5-repair"),
        ("pubmed", "pm-5-repair", "pm-verify"),
        ("pubmed", "pm-verify", "pm_eval"),
        ("pubmed", "pm_eval", "pm_fix"),
        ("pubmed", "pm_fix", "end"),
    ]
    for e in edges:
        cur.execute("INSERT INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (?, ?, ?)", e)
    conn.commit()
    conn.close()


def _ensure_pubmed_seed_ticket_wording() -> None:
    """Update legacy sample PubMed ticket wording to guideline-oriented wording."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """UPDATE tickets
           SET title = ?,
               description = ?,
               updated_at = ?
           WHERE category = 'PubMed_research'
             AND title = 'Fibrous dysplasia recent research'""",
        (
            "Fibrous dysplasia clinical guideline",
            "Please build a detailed, clinician-grade and patient-guiding management guideline for fibrous dysplasia (polyostotic and monostotic forms), based on PubMed evidence. Focus on end-to-end care pathway: initial suspicion, diagnostic workup, differential diagnosis, treatment selection (including bisphosphonates and denosumab where appropriate), contraindications, adverse-event monitoring, escalation criteria, follow-up schedule, and communication points for patients.",
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def run_seed_if_empty():
    """Load seed_data.json only when _seed_done is empty. Order: tickets → comments → tool_catalog → flow_definitions → flow_edges."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM _seed_done LIMIT 1")
    if cur.fetchone() is not None:
        conn.close()
        return
    path = Path(SEED_DATA_PATH)
    if not path.exists():
        cur.execute("INSERT INTO _seed_done (version) VALUES (?)", ("1",))
        conn.commit()
        conn.close()
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.now().isoformat()

    for t in data.get("tickets", []):
        cur.execute(
            """INSERT INTO tickets (title, description, status, resolution_summary, diagnostic_steps, reporter_name, created_at, updated_at, category)
               VALUES (?, ?, 'not_started', NULL, NULL, ?, ?, ?, ?)""",
            (
                t["title"],
                t["description"],
                t.get("reporter_name", "User"),
                now,
                now,
                t.get("category", "General"),
            ),
        )
    conn.commit()

    for c in data.get("comments", []):
        cur.execute(
            "INSERT INTO comments (ticket_id, author, content, created_at) VALUES (?, ?, ?, ?)",
            (c["ticket_id"], c["author"], c["content"], now),
        )
    conn.commit()

    for tc in data.get("tool_catalog", []):
        # database_flow_ensures.py already seeds the parent_pathway tools at
        # ensure_*_flow time, so the seed_data.json list can re-add overlapping
        # rows. OR IGNORE makes the seed idempotent.
        cur.execute(
            """INSERT OR IGNORE INTO tool_catalog (name, category, execution_mode, scope, enabled)
               VALUES (?, ?, ?, ?, ?)""",
            (
                tc["name"],
                tc.get("category", "General"),
                tc.get("execution_mode", "auto"),
                tc.get("scope", "operational"),
                tc.get("enabled", 1),
            ),
        )
    conn.commit()

    for fd in data.get("flow_definitions", []):
        # OR IGNORE: database_flow_ensures.py and similar bootstrap modules
        # already seed parent_pathway / doctor_finder flows on init, so re-applying
        # seed_data.json on the same DB must be idempotent.
        cur.execute(
            """INSERT OR IGNORE INTO flow_definitions (
                flow_key, node_id, node_type, label, description, prompt, loop_policy, execution_policy,
                max_retry, version, updated_at, prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close, python_source,
                http_url, http_method, http_headers, http_body, rag_operation, rag_body_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fd["flow_key"],
                fd["node_id"],
                fd["node_type"],
                fd["label"],
                fd.get("description"),
                fd.get("prompt"),
                fd.get("loop_policy", "none"),
                fd.get("execution_policy", "auto"),
                fd.get("max_retry", 3),
                fd.get("version", 1),
                now,
                fd.get("prompt_mode", "agentic"),
                fd.get("model_name"),
                fd.get("output_schema_key"),
                fd.get("output_schema"),
                1 if fd.get("agentic_step_close") else 0,
                fd.get("python_source"),
                fd.get("http_url"),
                fd.get("http_method"),
                fd.get("http_headers"),
                fd.get("http_body"),
                fd.get("rag_operation", "similar"),
                fd.get("rag_body_json"),
            ),
        )
    conn.commit()

    for fe in data.get("flow_edges", []):
        cur.execute(
            "INSERT OR IGNORE INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (?, ?, ?)",
            (fe["flow_key"], fe["source_node_id"], fe["target_node_id"]),
        )
    conn.commit()

    cur.execute("INSERT INTO _seed_done (version) VALUES (?)", ("1",))
    conn.commit()
    conn.close()
    _ensure_flow_texts_english()


# --- Tickets ---

def get_all_tickets():
    """Return all tickets."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, description, status, resolution_summary, diagnostic_steps, reporter_name, created_at, updated_at, category FROM tickets ORDER BY id"
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_ticket_by_id(ticket_id: int):
    """Return one ticket by id or None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, description, status, resolution_summary, diagnostic_steps, reporter_name, created_at, updated_at, category FROM tickets WHERE id = ?",
        (ticket_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def create_ticket(
    title: str,
    description: str,
    reporter_name: str = "User",
    category: str = "General",
) -> int:
    """Create a new ticket. Returns id."""
    now = datetime.now().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO tickets (title, description, status, resolution_summary, diagnostic_steps, reporter_name, created_at, updated_at, category)
           VALUES (?, ?, 'not_started', NULL, NULL, ?, ?, ?, ?)""",
        (title, description, reporter_name, now, now, category),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_ticket_status(
    ticket_id: int,
    summary: str,
    status: str,
    steps_taken: list[str],
) -> bool:
    """Update ticket status, summary and diagnostic steps (for MCP agent)."""
    if status not in ("not_started", "in_progress", "diagnosed"):
        return False
    now = datetime.now().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    steps_text = "\n".join(steps_taken) if steps_taken else None
    cur.execute(
        """UPDATE tickets SET resolution_summary = ?, status = ?, diagnostic_steps = ?, updated_at = ? WHERE id = ?""",
        (summary or None, status, steps_text, now, ticket_id),
    )
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def update_ticket(
    ticket_id: int,
    *,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    resolution_summary: str | None = None,
    diagnostic_steps: str | None = None,
    reporter_name: str | None = None,
    category: str | None = None,
) -> bool:
    """Update only provided ticket fields. Always sets updated_at. Returns True if found and updated."""
    if status is not None and status not in ("not_started", "in_progress", "diagnosed"):
        return False
    now = datetime.now().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    updates = ["updated_at = ?"]
    params = [now]
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if resolution_summary is not None:
        updates.append("resolution_summary = ?")
        params.append(resolution_summary)
    if diagnostic_steps is not None:
        updates.append("diagnostic_steps = ?")
        params.append(diagnostic_steps)
    if reporter_name is not None:
        updates.append("reporter_name = ?")
        params.append(reporter_name)
    if category is not None:
        updates.append("category = ?")
        params.append(category)
    if len(params) == 1:
        conn.close()
        return True
    params.append(ticket_id)
    cur.execute(f"UPDATE tickets SET {', '.join(updates)} WHERE id = ?", params)
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def reset_all_tickets_to_not_started() -> int:
    """Reset all tickets to status not_started and clear summaries. Returns row count."""
    now = datetime.now().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE tickets SET status = ?, resolution_summary = NULL, diagnostic_steps = NULL, updated_at = ?",
        ("not_started", now),
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def delete_ticket(ticket_id: int) -> bool:
    """Delete ticket. CASCADE removes comments. tool_requests.ticket_id set to NULL."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE tool_requests SET ticket_id = NULL, updated_at = ? WHERE ticket_id = ?", (datetime.now().isoformat(), ticket_id))
    cur.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


# --- Comments ---

def get_comments_for_ticket(ticket_id: int):
    """Return comments for ticket."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, ticket_id, author, content, created_at FROM comments WHERE ticket_id = ? ORDER BY created_at, id",
        (ticket_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_comment(ticket_id: int, author: str, content: str):
    """Add comment to ticket."""
    now = datetime.now().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO comments (ticket_id, author, content, created_at) VALUES (?, ?, ?, ?)",
        (ticket_id, author, content, now),
    )
    conn.commit()
    conn.close()


# --- Tool requests (missing-tool backlog) ---

def get_tool_requests(ticket_id: int | None = None):
    """Return tool requests, optionally filtered by ticket_id."""
    conn = get_connection()
    cur = conn.cursor()
    if ticket_id is not None:
        cur.execute(
            "SELECT id, name, status, similarity_key, note, ticket_id, builder_agent_id, created_at, updated_at FROM tool_requests WHERE ticket_id = ? ORDER BY id",
            (ticket_id,),
        )
    else:
        cur.execute(
            "SELECT id, name, status, similarity_key, note, ticket_id, builder_agent_id, created_at, updated_at FROM tool_requests ORDER BY id"
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_all_tool_requests() -> int:
    """Delete all tool_requests rows. Returns count deleted."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM tool_requests")
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def add_tool_request(
    name: str,
    note: str = "",
    ticket_id: int | None = None,
    status: str = "requested",
) -> int:
    """Store a missing-tool request. Returns created id. Deduplicates by (name, ticket_id) in requested/in_progress."""
    name = (name or "").strip()
    canonical = _to_tool_function_name(name)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, name FROM tool_requests
           WHERE ((? IS NULL AND ticket_id IS NULL) OR ticket_id = ?)
           AND status IN ('requested', 'in_progress')
           ORDER BY id""",
        (ticket_id, ticket_id),
    )
    rows = cur.fetchall() or []
    row = next(
        (
            r
            for r in rows
            if _to_tool_function_name((r.get("name") or "").strip()) == canonical
        ),
        None,
    )
    if row:
        conn.close()
        return row["id"]
    now = datetime.now().isoformat()
    cur.execute(
        """INSERT INTO tool_requests (name, status, note, ticket_id, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, status, note or "", ticket_id, now, now),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def delete_tool_catalog_by_names(names: list[str]) -> int:
    """Delete tool_catalog entries by name. Returns count deleted."""
    if not names:
        return 0
    cleaned = [str(n).strip() for n in names if n and str(n).strip()]
    if not cleaned:
        return 0
    conn = get_connection()
    cur = conn.cursor()
    placeholders = ", ".join(["?"] * len(cleaned))
    cur.execute(f"DELETE FROM tool_catalog WHERE name IN ({placeholders})", cleaned)
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def get_tool_request_by_id(request_id: int):
    """Return one tool_request by id or None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, status, similarity_key, note, ticket_id, builder_agent_id, created_at, updated_at FROM tool_requests WHERE id = ?",
        (request_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def claim_tool_request(request_id: int, builder_agent_id: str) -> dict:
    """
    Atomically claim a tool_request (requested -> in_progress) and set builder_agent_id.
    Returns {ok: True, request: {...}} or {ok: False, reason: "not_found_or_already_claimed"}.
    """
    now = datetime.now().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE tool_requests SET status = 'in_progress', builder_agent_id = ?, updated_at = ? "
        "WHERE id = ? AND status = 'requested'",
        (builder_agent_id, now, request_id),
    )
    if cur.rowcount != 1:
        conn.rollback()
        conn.close()
        return {"ok": False, "reason": "not_found_or_already_claimed"}
    conn.commit()
    cur.execute(
        "SELECT id, name, status, similarity_key, note, ticket_id, builder_agent_id, created_at, updated_at "
        "FROM tool_requests WHERE id = ?",
        (request_id,),
    )
    row = cur.fetchone()
    conn.close()
    return {"ok": True, "request": dict(row) if row else None}


def register_tool_status(
    request_id: int,
    status: str,
    branch: str | None = None,
    pr_url: str | None = None,
    similarity_key: str | None = None,
    implemented_name: str | None = None,
) -> dict:
    """Update tool_request status (+ similarity_key).

    Also record a row in tool_implementations for statuses that represent an implemented/generated tool.
    This is used by the Governance UI ("Zaimplementowane").
    """
    now = datetime.now().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE tool_requests SET status = ?, similarity_key = COALESCE(?, similarity_key), updated_at = ? "
        "WHERE id = ?",
        (status, similarity_key, now, request_id),
    )
    ok = cur.rowcount == 1
    conn.commit()
    if ok and (pr_url or status in ("ready_for_pr", "pr_created")):
        name = (implemented_name or "").strip() or f"request#{request_id}"
        cur.execute("SELECT id FROM tool_implementations WHERE name = ? ORDER BY id LIMIT 1", (name,))
        existing = cur.fetchone()
        if existing and existing.get("id") is not None:
            cur.execute(
                "UPDATE tool_implementations SET status = ?, pr_url = COALESCE(?, pr_url) WHERE id = ?",
                (status, pr_url, existing["id"]),
            )
        else:
            cur.execute(
                "INSERT INTO tool_implementations (name, status, pr_number, pr_url, created_at) VALUES (?, ?, ?, ?, ?)",
                (name, status, None, pr_url, now),
            )
        conn.commit()
    conn.close()
    return {"ok": ok, "request_id": request_id, "status": status, "branch": branch, "pr_url": pr_url}


# Backward compatibility with MCP / legacy API
def get_missing_tool_requests(ticket_id: int) -> list[dict]:
    """Alias: return tool_requests for ticket with suggested_tool_name, reason fields."""
    rows = get_tool_requests(ticket_id=ticket_id)
    return [
        {
            "id": r["id"],
            "ticket_id": r["ticket_id"],
            "suggested_tool_name": r["name"],
            "reason": r["note"] or "",
        }
        for r in rows
    ]


def add_missing_tool_request(ticket_id: int, tool_name: str, reason: str) -> bool:
    """Alias for MCP: save to tool_requests (name, note, ticket_id)."""
    name = (tool_name or "").strip()
    if not name:
        return False
    canonical = _to_tool_function_name(name)
    # If the tool already exists in the catalog, do not spam the backlog with "missing tool" requests.
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM tool_catalog")
        catalog_rows = cur.fetchall() or []
        exists = any(
            _to_tool_function_name((r.get("name") or "").strip()) == canonical
            for r in catalog_rows
        )
        conn.close()
    except Exception:
        exists = False
    if exists:
        return True
    add_tool_request(name=name, note=reason or "Brak powodu.", ticket_id=ticket_id)
    return True


# --- Tool catalog ---

def add_tool_to_catalog(
    name: str,
    category: str = "General",
    execution_mode: str = "auto",
    scope: str = "operational",
    enabled: int = 1,
) -> int | None:
    """
    Add a tool to the catalog (so it appears in MCP Tool Catalog and agent knows execution_mode).
    name must match the MCP tool function name (snake_case). Returns new id or None if name already exists.
    """
    name = (name or "").strip()
    if not name:
        return None
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM tool_catalog WHERE name = ?", (name,))
    if cur.fetchone():
        conn.close()
        return None
    cur.execute(
        "INSERT INTO tool_catalog (name, category, execution_mode, scope, enabled) VALUES (?, ?, ?, ?, ?)",
        (name, category or "General", execution_mode or "auto", scope or "operational", 1 if enabled else 0),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def get_tool_catalog(enabled_only: bool = True):
    """Return tool catalog (from seed or empty)."""
    conn = get_connection()
    cur = conn.cursor()
    if enabled_only:
        cur.execute("SELECT id, name, category, execution_mode, scope, enabled FROM tool_catalog WHERE enabled = 1 ORDER BY id")
    else:
        cur.execute("SELECT id, name, category, execution_mode, scope, enabled FROM tool_catalog ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tool_catalog_for_scope(scope: str, enabled_only: bool = True):
    """Return tool catalog filtered by scope (e.g. 'operational', 'builder')."""
    conn = get_connection()
    cur = conn.cursor()
    scope_val = (scope or "operational").strip()
    if enabled_only:
        cur.execute(
            "SELECT id, name, category, execution_mode, scope, enabled FROM tool_catalog WHERE enabled = 1 AND scope = ? ORDER BY id",
            (scope_val,),
        )
    else:
        cur.execute(
            "SELECT id, name, category, execution_mode, scope, enabled FROM tool_catalog WHERE scope = ? ORDER BY id",
            (scope_val,),
        )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tool_catalog_by_id(catalog_id: int):
    """Return one catalog entry by id or None."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, category, execution_mode, scope, enabled FROM tool_catalog WHERE id = ?",
        (catalog_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_tool_catalog_execution_mode(catalog_id: int, execution_mode: str) -> bool:
    """Update execution_mode (auto | approval) for catalog entry. Returns True if updated."""
    if execution_mode not in ("auto", "approval"):
        return False
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE tool_catalog SET execution_mode = ? WHERE id = ?", (execution_mode, catalog_id))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def get_tools_with_execution_mode(mode: str, enabled_only: bool = True) -> list[str]:
    """Return list of tool names from tool_catalog with given execution_mode (e.g. 'approval')."""
    catalog = get_tool_catalog(enabled_only=enabled_only)
    return [r["name"] for r in catalog if (r.get("execution_mode") or "").strip().lower() == mode.strip().lower()]


# --- Tool implementations ---

_PL_TO_ASCII = str.maketrans(
    "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ",
    "acelnoszzACELNOSZZ",
)


def canonicalize_tool_name(name: str) -> str:
    """Stable canonical key for tool-name deduplication across subsystems."""
    return _to_tool_function_name(name or "")


def _to_tool_function_name(name: str) -> str:
    s = (name or "").strip().translate(_PL_TO_ASCII).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "new_tool"
    if s[0].isdigit():
        s = f"tool_{s}"
    return s


def _backfill_tool_implementations_from_requests() -> None:
    """
    One-way sync: ensure tool_implementations has rows for tool_requests that are already implemented
    (e.g. 'ready_for_pr' without PR URL).
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, status, updated_at FROM tool_requests WHERE status IN ('ready_for_pr', 'pr_created') ORDER BY id"
    )
    rows = cur.fetchall() or []
    for r in rows:
        req_id = r.get("id")
        req_name = r.get("name") or ""
        status = r.get("status") or "ready_for_pr"
        impl_name = _to_tool_function_name(req_name)
        cur.execute("SELECT id FROM tool_implementations WHERE name = ? ORDER BY id LIMIT 1", (impl_name,))
        existing = cur.fetchone()
        if existing and existing.get("id") is not None:
            cur.execute("UPDATE tool_implementations SET status = ? WHERE id = ?", (status, existing["id"]))
        else:
            cur.execute(
                "INSERT INTO tool_implementations (name, status, pr_number, pr_url, created_at) VALUES (?, ?, ?, ?, ?)",
                (impl_name, status, None, None, r.get("updated_at") or datetime.now().isoformat()),
            )
    conn.commit()
    conn.close()


def get_tool_implementations():
    """Return list of implemented tools (PR/merged)."""
    _backfill_tool_implementations_from_requests()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, status, pr_number, pr_url, created_at FROM tool_implementations ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Flow definitions ---

def _ensure_position_columns():
    """Add position_x, position_y to flow_definitions if missing (existing DBs)."""
    conn = get_connection()
    cur = conn.cursor()
    for col in ("position_x", "position_y"):
        try:
            cur.execute(f"ALTER TABLE flow_definitions ADD COLUMN {col} REAL")
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()
        finally:
            pass
    conn.close()


def _ensure_flow_execution_columns():
    """prompt_mode, model_name, output_schema_key — LLM Simple vs Agentic + model override (docs/03)."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE flow_definitions ADD COLUMN prompt_mode TEXT NOT NULL DEFAULT 'agentic'")
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    try:
        cur.execute("ALTER TABLE flow_definitions ADD COLUMN model_name TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    try:
        cur.execute("ALTER TABLE flow_definitions ADD COLUMN output_schema_key TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    # One-time: operational op-1 = LLM Call (Simple) + ai_summary preset
    try:
        cur.execute(
            """UPDATE flow_definitions SET prompt_mode = 'simple', output_schema_key = 'ai_summary'
               WHERE flow_key = 'operational' AND node_id = 'op-1'
               AND (output_schema_key IS NULL OR output_schema_key = '')"""
        )
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    # Legacy seed: op-1 used to call set_ai_summary — swap to Simple (no tools).
    _op1_simple_prompt = (
        "Based on ticket title, description, and discussion (if present), generate a summary: "
        "field `issue` - one concise sentence describing the problem; field `work_log_summary` - a short work log for the technician. "
        "Use only ticket text. Do not use MCP tools. "
        "You may reference context: {{ context.initial.title }}, {{ context.initial.description }}, {{ context.initial.comments_text }}."
    )
    try:
        cur.execute(
            """UPDATE flow_definitions SET prompt = ?, prompt_mode = 'simple', output_schema_key = 'ai_summary'
               WHERE flow_key = 'operational' AND node_id = 'op-1'
               AND prompt LIKE '%set_ai_summary%'""",
            (_op1_simple_prompt,),
        )
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    conn.close()


def _ensure_output_schema_column():
    """output_schema TEXT — JSON field definitions for LLM Simple."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE flow_definitions ADD COLUMN output_schema TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    conn.close()


def _ensure_agentic_step_close_column():
    """agentic_step_close INTEGER — second LLM after an agentic step: success/error/step_summary."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "ALTER TABLE flow_definitions ADD COLUMN agentic_step_close INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    conn.close()


def _ensure_python_source_column():
    """python_source TEXT — Python source for the code node type (Code / Function node)."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE flow_definitions ADD COLUMN python_source TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    conn.close()


def _ensure_step_name_column():
    """step_name TEXT — dispatch key for doctor_finder_step executor nodes."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE flow_definitions ADD COLUMN step_name TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    conn.close()


def _ensure_http_request_columns():
    """http_url, http_method, http_headers, http_body — HTTP Request (REST) node."""
    conn = get_connection()
    cur = conn.cursor()
    for col_sql in (
        "ALTER TABLE flow_definitions ADD COLUMN http_url TEXT",
        "ALTER TABLE flow_definitions ADD COLUMN http_method TEXT",
        "ALTER TABLE flow_definitions ADD COLUMN http_headers TEXT",
        "ALTER TABLE flow_definitions ADD COLUMN http_body TEXT",
    ):
        try:
            cur.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()
    conn.close()


def _ensure_rag_assist_columns():
    """rag_operation, rag_body_json — RAG (assistive retrieval) node."""
    conn = get_connection()
    cur = conn.cursor()
    for col_sql in (
        "ALTER TABLE flow_definitions ADD COLUMN rag_operation TEXT",
        "ALTER TABLE flow_definitions ADD COLUMN rag_body_json TEXT",
    ):
        try:
            cur.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()
    conn.close()


def _ensure_merge_columns():
    """merge_strategy, merge_fields, merge_key_field — Merge node."""
    conn = get_connection()
    cur = conn.cursor()
    for col_sql in (
        "ALTER TABLE flow_definitions ADD COLUMN merge_strategy TEXT",
        "ALTER TABLE flow_definitions ADD COLUMN merge_fields TEXT",
        "ALTER TABLE flow_definitions ADD COLUMN merge_key_field TEXT",
    ):
        try:
            cur.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()
    conn.close()


def _ensure_integration_columns():
    """integration_* — integration node (chat/issue-tracker/identity/email)."""
    conn = get_connection()
    cur = conn.cursor()
    for col_sql in (
        "ALTER TABLE flow_definitions ADD COLUMN integration_operation TEXT",
        "ALTER TABLE flow_definitions ADD COLUMN integration_params_json TEXT",
        "ALTER TABLE flow_definitions ADD COLUMN integration_credentials_json TEXT",
    ):
        try:
            cur.execute(col_sql)
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()
    conn.close()


def _ensure_flow_texts_english():
    """
    One-time-safe text migration for seeded flow labels/descriptions.
    Keeps behavior unchanged and only normalizes user-facing wording to English.
    """
    conn = get_connection()
    cur = conn.cursor()
    updates = [
        (
            "operational",
            "start",
            "Start",
            "Flow entry point.",
            "After ticket.created, pass ticket context (id, summary, description, discussion) to the next node (AI Summary).",
        ),
        (
            "operational",
            "op-1",
            "AI Summary",
            "Issue and work log summary",
            "Based on ticket title, description, and discussion, call set_ai_summary(issue=..., work_log_summary=...).",
        ),
        (
            "operational",
            "op-2",
            "Diagnosis",
            "Diagnosis with MCP tools",
            "Use list_available_tools(), then ping_ip, get_server_logs, etc. If a tool is missing, call request_missing_tool.",
        ),
        (
            "operational",
            "op-3",
            "Status update",
            "Persist result",
            "Always call update_ticket_status(ticket_id, summary, status, steps_taken) at the end.",
        ),
        (
            "operational",
            "end",
            "End",
            "Flow completion.",
            "End of flow: diagnosis completed. Ensure update_ticket_status was called with summary and steps_taken.",
        ),
        (
            "builder",
            "bl-1",
            "Watch Queue",
            "Monitors the queue of reported missing tools.",
            "Listen for events on the MCP tool_requests queue. Priority: oldest unreserved items. Skip items with status != 'requested'.",
        ),
        (
            "builder",
            "bl-2",
            "Reserve Request",
            "Atomically reserves a task.",
            "Reserve one task from the queue (atomic claim). Assign builder_agent_id. If reservation fails (race condition), return to Watch Queue.",
        ),
        (
            "builder",
            "bl-3",
            "Similarity Check",
            "Checks whether a similar tool already exists.",
            "Check whether a semantically equivalent tool exists in MCP catalog and open PRs. Use embedding similarity (threshold 0.85). If matched, mark as duplicate and link the existing one.",
        ),
        (
            "builder",
            "bl-4",
            "Read KB + Repo",
            "Reads standards and analyzes the codebase.",
            "Fetch coding standards from Knowledge Base, check naming conventions, analyze repository structure, and note patterns for logging/config/error handling/input validation.",
        ),
        (
            "builder",
            "bl-5",
            "Branch + Placement",
            "Creates a branch and decides where to place the tool.",
            "Create feature branch tool/<tool_name>. Based on repository analysis choose the target module/folder and implementation path.",
        ),
        (
            "builder",
            "bl-6",
            "Implement Tool",
            "Generates MCP tool code.",
            "Generate MCP tool code with structured logging, env-based config, input validation, error handling, decorators, deterministic JSON output, and test skeleton.",
        ),
        (
            "builder",
            "bl-7",
            "Create PR",
            "Opens a pull request with description.",
            "Commit implementation, push feature branch, then open PR via GitHub API with title [Tool] <tool_name> and technical summary.",
        ),
        (
            "builder",
            "bl-8",
            "Register Tool",
            "Stores tool status and PR link in registry.",
            "Update tool registry with status=pr_created, branch, pr_url, timestamp, and builder_agent_id.",
        ),
        (
            "builder",
            "bl-9",
            "Notify Queue",
            "Notifies operational system about a new tool.",
            "Set request status to pr_created, emit event to operational system, and include tool in the next Tools Snapshot.",
        ),
    ]
    for flow_key, node_id, label_en, desc_en, prompt_en in updates:
        cur.execute(
            """UPDATE flow_definitions
               SET label = ?, description = ?, prompt = ?
               WHERE flow_key = ? AND node_id = ?""",
            (label_en, desc_en, prompt_en, flow_key, node_id),
        )
    conn.commit()
    conn.close()


def get_flow_keys():
    """Return distinct flow_key list."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT flow_key FROM flow_definitions ORDER BY flow_key")
    rows = cur.fetchall()
    conn.close()
    return [str(r["flow_key"]) for r in rows]


def get_flow_definition_nodes(flow_key: str):
    """Return flow nodes (rows from flow_definitions)."""
    _ensure_position_columns()
    _ensure_flow_execution_columns()
    _ensure_output_schema_column()
    _ensure_agentic_step_close_column()
    _ensure_python_source_column()
    _ensure_step_name_column()
    _ensure_http_request_columns()
    _ensure_rag_assist_columns()
    _ensure_merge_columns()
    _ensure_integration_columns()
    _ensure_evaluation_source_nodes_column()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT flow_key, node_id, node_type, label, description, prompt, loop_policy, execution_policy,
                  max_retry, version, updated_at, position_x, position_y, prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close, python_source, step_name,
                  http_url, http_method, http_headers, http_body, rag_operation, rag_body_json,
                  merge_strategy, merge_fields, merge_key_field, integration_operation, integration_params_json, integration_credentials_json,
                  evaluation_source_nodes_json
           FROM flow_definitions WHERE flow_key = ? ORDER BY id""",
        (flow_key,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_flow_edges(flow_key: str):
    """Return flow edges."""
    _ensure_flow_edge_label_column()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT flow_key, source_node_id, target_node_id, label FROM flow_edges WHERE flow_key = ? ORDER BY id",
        (flow_key,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_flow_node(flow_key: str, node_id: str):
    """Return one node (flow_key, node_id) or None."""
    _ensure_flow_execution_columns()
    _ensure_output_schema_column()
    _ensure_agentic_step_close_column()
    _ensure_python_source_column()
    _ensure_step_name_column()
    _ensure_http_request_columns()
    _ensure_rag_assist_columns()
    _ensure_merge_columns()
    _ensure_integration_columns()
    _ensure_evaluation_source_nodes_column()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT flow_key, node_id, node_type, label, description, prompt, loop_policy, execution_policy,
                  max_retry, version, updated_at, position_x, position_y, prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close, python_source, step_name,
                  http_url, http_method, http_headers, http_body, rag_operation, rag_body_json,
                  merge_strategy, merge_fields, merge_key_field, integration_operation, integration_params_json, integration_credentials_json,
                  evaluation_source_nodes_json
           FROM flow_definitions WHERE flow_key = ? AND node_id = ?""",
        (flow_key, node_id),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_flow_node(
    flow_key: str,
    node_id: str,
    *,
    prompt: str | None = None,
    loop_policy: str | None = None,
    execution_policy: str | None = None,
    max_retry: int | None = None,
    description: str | None = None,
    label: str | None = None,
    position_x: float | None = None,
    position_y: float | None = None,
    prompt_mode: str | None = None,
    model_name: str | None = None,
    output_schema_key: str | None = None,
    output_schema: str | None = None,
    agentic_step_close: int | bool | None = None,
    python_source: str | None = None,
    http_url: str | None = None,
    http_method: str | None = None,
    http_headers: str | None = None,
    http_body: str | None = None,
    rag_operation: str | None = None,
    rag_body_json: str | None = None,
    merge_strategy: str | None = None,
    merge_fields: str | None = None,
    merge_key_field: str | None = None,
    integration_operation: str | None = None,
    integration_params_json: str | None = None,
    integration_credentials_json: str | None = None,
) -> dict | None:
    """
    Update given node fields. Always sets updated_at and increments version.
    Returns updated row (dict) or None if node does not exist.
    """
    node = get_flow_node(flow_key, node_id)
    if not node:
        return None
    now = datetime.now().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    updates = ["updated_at = ?", "version = version + 1"]
    params = [now]
    if prompt is not None:
        updates.append("prompt = ?")
        params.append(prompt)
    if loop_policy is not None:
        updates.append("loop_policy = ?")
        params.append(loop_policy)
    if execution_policy is not None:
        updates.append("execution_policy = ?")
        params.append(execution_policy)
    if max_retry is not None:
        updates.append("max_retry = ?")
        params.append(max_retry)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if label is not None:
        updates.append("label = ?")
        params.append(label)
    if position_x is not None:
        updates.append("position_x = ?")
        params.append(position_x)
    if position_y is not None:
        updates.append("position_y = ?")
        params.append(position_y)
    if prompt_mode is not None:
        updates.append("prompt_mode = ?")
        params.append(prompt_mode)
    if model_name is not None:
        updates.append("model_name = ?")
        params.append(model_name)
    if output_schema_key is not None:
        updates.append("output_schema_key = ?")
        params.append(output_schema_key)
    if output_schema is not None:
        updates.append("output_schema = ?")
        params.append(output_schema if str(output_schema).strip() else None)
    if agentic_step_close is not None:
        updates.append("agentic_step_close = ?")
        params.append(1 if agentic_step_close else 0)
    if python_source is not None:
        updates.append("python_source = ?")
        params.append(python_source if str(python_source).strip() else None)
    if http_url is not None:
        updates.append("http_url = ?")
        params.append(http_url if str(http_url).strip() else None)
    if http_method is not None:
        updates.append("http_method = ?")
        params.append(http_method if str(http_method).strip() else None)
    if http_headers is not None:
        updates.append("http_headers = ?")
        params.append(http_headers if str(http_headers).strip() else None)
    if http_body is not None:
        updates.append("http_body = ?")
        params.append(http_body if str(http_body).strip() else None)
    if rag_operation is not None:
        updates.append("rag_operation = ?")
        params.append(rag_operation.strip() or None)
    if rag_body_json is not None:
        updates.append("rag_body_json = ?")
        params.append(rag_body_json if str(rag_body_json).strip() else None)
    if merge_strategy is not None:
        updates.append("merge_strategy = ?")
        params.append(merge_strategy.strip() or None)
    if merge_fields is not None:
        updates.append("merge_fields = ?")
        params.append(merge_fields if str(merge_fields).strip() else None)
    if merge_key_field is not None:
        updates.append("merge_key_field = ?")
        params.append(merge_key_field.strip() or None)
    if integration_operation is not None:
        updates.append("integration_operation = ?")
        params.append(integration_operation.strip() or None)
    if integration_params_json is not None:
        updates.append("integration_params_json = ?")
        params.append(integration_params_json if str(integration_params_json).strip() else None)
    if integration_credentials_json is not None:
        updates.append("integration_credentials_json = ?")
        params.append(integration_credentials_json if str(integration_credentials_json).strip() else None)
    params.extend([flow_key, node_id])
    cur.execute(f"UPDATE flow_definitions SET {', '.join(updates)} WHERE flow_key = ? AND node_id = ?", params)
    conn.commit()
    conn.close()
    return get_flow_node(flow_key, node_id)


def _next_node_id(flow_key: str) -> str:
    """Generate next node_id for flow (op-4, op-5 for operational; bl-10, bl-11 for builder)."""
    prefix = "op-" if flow_key == "operational" else "bl-"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT node_id FROM flow_definitions WHERE flow_key = ? AND node_id LIKE ?",
        (flow_key, f"{prefix}%"),
    )
    rows = cur.fetchall()
    conn.close()
    max_n = 0
    for row in rows:
        nid = row["node_id"] if isinstance(row, dict) else row[0]
        try:
            suffix = nid[len(prefix) :].strip()
            if suffix.isdigit():
                max_n = max(max_n, int(suffix))
        except Exception:
            pass
    return f"{prefix}{max_n + 1}"


def create_flow_node(
    flow_key: str,
    *,
    node_type: str = "action",
    label: str = "New node",
    description: str | None = None,
    prompt: str | None = None,
    loop_policy: str = "none",
    execution_policy: str = "auto",
    max_retry: int = 3,
    python_source: str | None = None,
    http_url: str | None = None,
    http_method: str | None = None,
    http_headers: str | None = None,
    http_body: str | None = None,
    rag_operation: str | None = None,
    rag_body_json: str | None = None,
    merge_strategy: str | None = None,
    merge_fields: str | None = None,
    merge_key_field: str | None = None,
    integration_operation: str | None = None,
    integration_params_json: str | None = None,
    integration_credentials_json: str | None = None,
) -> dict | None:
    """Create a new flow node. Returns the created row (dict) or None on error.
    Retries on UNIQUE (race when two requests get the same node_id)."""
    now = datetime.now().isoformat()
    vals = (
        node_type or "action",
        label or "New node",
        description or "",
        prompt or "",
        loop_policy or "none",
        execution_policy or "auto",
        max_retry if max_retry is not None else 3,
        1,  # version
        now,
    )
    for _ in range(5):
        node_id = _next_node_id(flow_key)
        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """INSERT INTO flow_definitions (
                    flow_key, node_id, node_type, label, description, prompt, loop_policy, execution_policy,
                    max_retry, version, updated_at, prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close, python_source,
                    http_url, http_method, http_headers, http_body, rag_operation, rag_body_json,
                    merge_strategy, merge_fields, merge_key_field,
                    integration_operation, integration_params_json, integration_credentials_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'agentic', NULL, NULL, NULL, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (flow_key, node_id)
                + vals
                + (
                    python_source if python_source and str(python_source).strip() else None,
                    http_url if http_url and str(http_url).strip() else None,
                    http_method if http_method and str(http_method).strip() else None,
                    http_headers if http_headers and str(http_headers).strip() else None,
                    http_body if http_body and str(http_body).strip() else None,
                    (rag_operation or "similar").strip() or "similar",
                    rag_body_json if rag_body_json and str(rag_body_json).strip() else None,
                    (merge_strategy or "append").strip() or "append",
                    merge_fields if merge_fields and str(merge_fields).strip() else "[]",
                    merge_key_field if merge_key_field and str(merge_key_field).strip() else "id",
                    integration_operation if integration_operation and str(integration_operation).strip() else "",
                    integration_params_json if integration_params_json and str(integration_params_json).strip() else "{}",
                    integration_credentials_json
                    if integration_credentials_json and str(integration_credentials_json).strip()
                    else "",
                ),
            )
            conn.commit()
            conn.close()
            return get_flow_node(flow_key, node_id)
        except sqlite3.IntegrityError:
            conn.rollback()
            conn.close()
            # UNIQUE (flow_key, node_id) – race with another insert; retry with new id
        except Exception:
            conn.rollback()
            conn.close()
            raise
    return None


def delete_flow_node(flow_key: str, node_id: str) -> bool:
    """Delete flow node and all edges involving it. Returns True if node was deleted."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM flow_edges WHERE flow_key = ? AND (source_node_id = ? OR target_node_id = ?)", (flow_key, node_id, node_id))
    cur.execute("DELETE FROM flow_definitions WHERE flow_key = ? AND node_id = ?", (flow_key, node_id))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n > 0


def create_flow_edge(flow_key: str, source_node_id: str, target_node_id: str, label: str | None = None) -> dict | None:
    """Create edge. Returns dict with flow_key, source_node_id, target_node_id or None if duplicate/invalid."""
    if not source_node_id or not target_node_id or source_node_id == target_node_id:
        return None
    conn = get_connection()
    cur = conn.cursor()
    try:
        _ensure_flow_edge_label_column()
        cur.execute(
            "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id, label) VALUES (?, ?, ?, ?)",
            (flow_key, source_node_id, target_node_id, label),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return None
    conn.close()
    return {"flow_key": flow_key, "source_node_id": source_node_id, "target_node_id": target_node_id, "label": label}


def _ensure_flow_edge_label_column():
    """label TEXT on flow_edges for decision routing (true/false/unlabeled)."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE flow_edges ADD COLUMN label TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    conn.close()


def _ensure_evaluation_source_nodes_column() -> None:
    """evaluation_source_nodes_json — JSON list of node_ids for evaluation_check synthesis sources."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE flow_definitions ADD COLUMN evaluation_source_nodes_json TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    conn.close()


_PUBMED_EVAL_SOURCE_NODES_JSON = '["pm-4-build", "pm-5-repair"]'


def _ensure_pubmed_eval_tail() -> None:
    """Idempotent: pm_eval → pm_fix after PMID verification (nodes, edges, source JSON)."""
    _ensure_evaluation_source_nodes_column()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM flow_definitions WHERE flow_key = 'pubmed' AND node_id = 'pm_eval' LIMIT 1"
    )
    if cur.fetchone() is None:
        conn.close()
        _ensure_pubmed_flow()
        return

    cur.execute(
        """UPDATE flow_definitions SET evaluation_source_nodes_json = ?
           WHERE flow_key = 'pubmed' AND node_id = 'pm_eval'""",
        (_PUBMED_EVAL_SOURCE_NODES_JSON,),
    )
    cur.execute(
        "DELETE FROM flow_edges WHERE flow_key = 'pubmed' AND source_node_id = 'pm-verify' AND target_node_id = 'end'"
    )
    for source_id, target_id in (
        ("pm-verify", "pm_eval"),
        ("pm_eval", "pm_fix"),
        ("pm_fix", "end"),
    ):
        cur.execute(
            """SELECT 1 FROM flow_edges
               WHERE flow_key = 'pubmed' AND source_node_id = ? AND target_node_id = ? LIMIT 1""",
            (source_id, target_id),
        )
        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO flow_edges (flow_key, source_node_id, target_node_id) VALUES (?, ?, ?)",
                ("pubmed", source_id, target_id),
            )
    conn.commit()
    conn.close()


def _ensure_guidelines_rag_column():
    """guidelines_rag_anchor_pmids_json — per-node anchor PMID override for guidelines_rag."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE flow_definitions ADD COLUMN guidelines_rag_anchor_pmids_json TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        conn.rollback()
    conn.close()


def delete_flow_edge(flow_key: str, source_node_id: str, target_node_id: str) -> bool:
    """Delete one edge. Returns True if deleted."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM flow_edges WHERE flow_key = ? AND source_node_id = ? AND target_node_id = ?",
        (flow_key, source_node_id, target_node_id),
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n > 0


if __name__ == "__main__":
    init_db()
    run_seed_if_empty()
    print("Schema OK. Seed (if empty) done. Tickets:", len(get_all_tickets()))
