"""Schema as code — SQLAlchemy 2.0 Core ``Table`` definitions.

Every persistent table the backend knows about is declared here against a
single :data:`metadata` instance. Alembic targets that ``metadata`` for
autogeneration.

**Scope today (Phase 1):** the *content* domain tables, because they are the
first module migrated to the new persistence layer (see
``backend/content/``). Other tables (``tickets``, ``flow_definitions``,
``doctor_finder_run_results``, …) are still created and used by
``backend/database.py`` directly; they will be declared here as their owning
modules get refactored.

The column types and nullability below match exactly the ``CREATE TABLE``
statements in ``backend/content_db.py`` so that the existing data on disk
remains valid for the new Core-based repositories.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)

# Naming convention so that Alembic generates predictable constraint names
# and downgrade migrations remain reversible.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


# -- content domain -----------------------------------------------------------

diseases = Table(
    "diseases",
    metadata,
    Column("slug", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("name_short", Text, nullable=False),
    Column("omim", Text, nullable=False),
    Column("gene", Text, nullable=False),
    Column("inheritance", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("types_json", Text, nullable=False, server_default="[]"),
    Column("related_json", Text, nullable=False, server_default="[]"),
    Column("prevalence_text", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("status_by", Text),
    Column("status_date", Text),
    Column("ai_draft_date", Text),
    Column("open_prs", Integer, nullable=False, server_default="0"),
    Column("doctors_count", Integer, nullable=False, server_default="0"),
    Column("trials_count", Integer, nullable=False, server_default="0"),
    Column("coverage", Text, nullable=False),
    Column("accent", Text, nullable=False),
    Column(
        "guideline_prompt_profile_json",
        Text,
        nullable=False,
        server_default="{}",
    ),
)


guideline_documents = Table(
    "guideline_documents",
    metadata,
    Column(
        "disease_slug",
        Text,
        ForeignKey("diseases.slug", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("version", Text, nullable=False),
    Column("locale", Text, nullable=False, server_default="en"),
    Column("section_count", Integer, nullable=False, server_default="0"),
    Column("last_reviewed", Text),
    Column("sections_json", Text),
)


catalog_stats = Table(
    "catalog_stats",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("disease_count", Integer, nullable=False),
    Column("doctor_count", Integer, nullable=False),
    Column("recruiting_trial_count", Integer, nullable=False),
    Column("open_pr_count", Integer, nullable=False),
    CheckConstraint("id = 1", name="single_row"),
)


content_prs = Table(
    "content_prs",
    metadata,
    Column("id", Text, primary_key=True),
    Column(
        "disease_slug",
        Text,
        ForeignKey("diseases.slug"),
        nullable=False,
    ),
    Column("title", Text, nullable=False),
    Column("opened", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("author", Text, nullable=False, server_default="AI Watcher"),
    Column("reviewer", Text),
    Column("summary", Text, nullable=False),
    Column("citations_count", Integer, nullable=False, server_default="0"),
    Column("diff_json", Text, nullable=False, server_default="[]"),
    Column("papers_json", Text, nullable=False, server_default="[]"),
)


care_pathways = Table(
    "care_pathways",
    metadata,
    Column(
        "disease_slug",
        Text,
        ForeignKey("diseases.slug", ondelete="CASCADE"),
        nullable=False,
    ),
    # Multi-kind pathways — a parent navigates each independently: how to
    # confirm the diagnosis, what to monitor over time, what to do on
    # treatment or after surgery. Existing single rows default to
    # 'diagnosis'; the migration on a populated DB happens via the alter
    # in content_db.ensure_content_schema.
    Column("kind", Text, nullable=False, server_default="diagnosis"),
    Column("locale", Text, nullable=False, server_default="en"),
    Column("version", Text, nullable=False),
    Column("based_on", Text, nullable=False),
    Column("generated_at", Text, nullable=False),
    Column("source_guideline_version", Text),
    Column("source_execution_id", Text),
    Column("tree_json", Text, nullable=False),
    Column("draft_tree_json", Text),
    Column("draft_updated_at", Text),
    PrimaryKeyConstraint("disease_slug", "kind", name="pk_care_pathways"),
    CheckConstraint(
        "kind IN ('diagnosis','monitoring','post_treatment')",
        name="care_pathway_kind_enum",
    ),
)


trials = Table(
    "trials",
    metadata,
    Column("nct", Text, primary_key=True),
    Column("title", Text, nullable=False),
    Column("phase", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("sponsor", Text, nullable=False),
    Column("city", Text),
    Column("country", Text),
    Column("lat", Float),
    Column("lng", Float),
    Column("age_range", Text),
    Column("principal_investigator", Text),
    Column("eligibility_summary", Text, nullable=False, server_default=""),
    Column("enrollment_target", Integer),
    Column("enrolled", Integer),
    Column("contact", Text),
    Column("last_seen", Text),
)


disease_trials = Table(
    "disease_trials",
    metadata,
    Column(
        "disease_slug",
        Text,
        ForeignKey("diseases.slug", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "nct",
        Text,
        ForeignKey("trials.nct", ondelete="CASCADE"),
        nullable=False,
    ),
    PrimaryKeyConstraint("disease_slug", "nct", name="pk_disease_trials"),
)


therapies = Table(
    "therapies",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "disease_slug",
        Text,
        ForeignKey("diseases.slug", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("name", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("note", Text, nullable=False, server_default=""),
    Column("sort_order", Integer, nullable=False, server_default="100"),
    CheckConstraint(
        "status IN ('consensus','verified','pending','preclinical')",
        name="therapy_status_enum",
    ),
)


foundations = Table(
    "foundations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False, unique=True),
    Column("scope", Text, nullable=False),
    Column("url", Text, nullable=False, server_default=""),
    Column("city", Text),
    Column("country", Text),
    Column("services_json", Text, nullable=False, server_default="[]"),
)


disease_foundations = Table(
    "disease_foundations",
    metadata,
    Column(
        "disease_slug",
        Text,
        ForeignKey("diseases.slug", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "foundation_id",
        Integer,
        ForeignKey("foundations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    PrimaryKeyConstraint(
        "disease_slug", "foundation_id", name="pk_disease_foundations"
    ),
)


# Pointer to the international consensus paper for each disease — the
# "ground truth" the AI-maintained living document is read against. Filled
# either by the find-the-consensus workflow (Gemma 4 ranking) or by a
# reviewer asserting "yes, this is the paper". The pointer is paragraph 0
# of every disease detail page: parents and clinicians see the recognised
# document name before they see anything the system proposes on top.
official_guideline_pointers = Table(
    "official_guideline_pointers",
    metadata,
    Column(
        "disease_slug",
        Text,
        ForeignKey("diseases.slug", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("title", Text, nullable=False),
    Column("authors", Text, nullable=False),
    Column("year", Integer, nullable=False),
    Column("journal", Text, nullable=False),
    Column("pmid", Text, nullable=False),
    Column("url", Text, nullable=False, server_default=""),
    Column("summary", Text, nullable=False, server_default=""),
    Column("confirmed_by", Text, nullable=False, server_default=""),
    Column("confirmed_at", Text, nullable=False),
    Column("source", Text, nullable=False, server_default="reviewer"),
    CheckConstraint(
        "source IN ('reviewer','workflow','seed')",
        name="official_guideline_source_enum",
    ),
)


# Private case context uploaded by a parent / clinician. We store the
# Gemma-extracted, PII-free JSON. The original text is held only in memory
# while the redaction runs and is discarded immediately afterwards — the
# raw bytes never reach disk and never reach the synthesis model. The
# SHA-256 of the original bytes is kept as the only fingerprint, so two
# uploads of the same document can be matched without knowing their
# content.
private_contexts = Table(
    "private_contexts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "disease_slug",
        Text,
        ForeignKey("diseases.slug", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("original_filename", Text, nullable=False),
    Column("original_chars", Integer, nullable=False, server_default="0"),
    Column("original_sha256", Text, nullable=False, server_default=""),
    Column("uploaded_at", Text, nullable=False),
    Column("redacted_json", Text, nullable=False, server_default="{}"),
    Column("pii_tokens_removed", Integer, nullable=False, server_default="0"),
    Column("clinical_facts_extracted", Integer, nullable=False, server_default="0"),
    Column("model_used", Text, nullable=False, server_default=""),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("error", Text),
    CheckConstraint(
        "status IN ('pending','ready','failed')",
        name="private_context_status_enum",
    ),
)


# -- disease_index domain -----------------------------------------------------
#
# Global catalogue of every rare disease the platform might suggest in the
# "Add a disease" autocomplete — ~10k rows after Orphanet seed. Distinct from
# the ``diseases`` table above: an entry here becomes a ``diseases`` row only
# after the bootstrap workflow has been run for it. ``local_slug`` is the
# soft link back to that local record once it exists.
#
# ``is_in_scope`` is the genetic / non-genetic gate: rare infectious or
# multifactorial diseases are kept in the index (so the UI can answer "yes,
# Tuberculosis exists, but it is out of scope for GeneGuidelines"), they are
# just rendered with an out-of-scope badge instead of the "Run research"
# button.
disease_index = Table(
    "disease_index",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("primary_id", Text, nullable=False, unique=True),  # e.g. "ORPHA:558"
    Column("source", Text, nullable=False, server_default="manual"),
    Column("canonical_name", Text, nullable=False),
    Column("canonical_name_norm", Text, nullable=False),
    Column("category", Text),  # null until classified
    Column("is_in_scope", Boolean, nullable=False, server_default=text("true")),
    Column("inheritance", Text),
    Column("summary", Text, nullable=False, server_default=""),
    Column("omim_codes_json", Text, nullable=False, server_default="[]"),
    Column("gene_symbols_json", Text, nullable=False, server_default="[]"),
    Column("orpha_url", Text),
    Column("omim_url", Text),
    # Soft link to ``diseases.slug`` when the bootstrap workflow has been
    # run for this entry — no FK, because a deleted local record should not
    # cascade-delete the (still authoritative) external index row.
    Column("local_slug", Text),
    Column("source_version", Text),
    Column("refreshed_at", Text, nullable=False),
    CheckConstraint(
        "source IN ('orphanet','mondo','gard','manual')",
        name="disease_index_source_enum",
    ),
    CheckConstraint(
        "category IS NULL OR category IN ("
        "'genetic','predominantly_genetic','multifactorial',"
        "'infectious','acquired','unknown')",
        name="disease_index_category_enum",
    ),
)

# Searchable terms (canonical name, synonyms, gene, OMIM, ORPHA, ICD-10 …)
# stored as one row per (entry, alias, kind, locale). The ``alias_norm`` is
# always lower-cased and ASCII-folded so a single ILIKE / pg_trgm pass
# matches across diacritics and casing.
disease_index_aliases = Table(
    "disease_index_aliases",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "disease_id",
        Integer,
        ForeignKey("disease_index.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("alias", Text, nullable=False),
    Column("alias_norm", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("locale", Text),
    Column("weight", Float, nullable=False, server_default="1.0"),
    UniqueConstraint(
        "disease_id",
        "alias_norm",
        "kind",
        "locale",
        name="uq_alias_per_kind_locale",
    ),
    CheckConstraint(
        "kind IN ('canonical','synonym','omim','gene','orpha','icd10','locale_name')",
        name="alias_kind_enum",
    ),
)

# Searches issue a fuzzy match against ``alias_norm``; this index is the
# single hot path for ``GET /api/disease-index/suggest``.
Index(
    "ix_disease_index_aliases_alias_norm",
    disease_index_aliases.c.alias_norm,
)

Index(
    "ix_disease_index_canonical_name_norm",
    disease_index.c.canonical_name_norm,
)


# -- evidence audit domain ----------------------------------------------------
#
# Two tables that together form the audit-grade record of *what the AI knew
# and decided* for each disease over time. Written by major workflow runs
# (``pubmed`` guideline draft, ``incremental_guideline_update`` from F7,
# parent-pathway flows from F6) and read by the public timeline endpoint
# plus the upcoming admin evidence dashboard (F8 v0.2).
#
# Why two tables instead of one big one:
# - ``disease_evidence_snapshots`` is the aggregate. One row per run that
#   touches literature for a disease; the series of rows for a disease is
#   a sparkline-ready timeline (article counts, citation counts, knowledge
#   gaps, quality / confidence scores).
# - ``article_category_audits`` is the per-article ledger. One row per
#   (PMID, disease, execution_id) capturing the categorisation Gemma 4
#   applied during triage plus optional reviewer override. Joins to the
#   snapshot via ``triggered_by_execution_id`` when needed.
#
# Category vocabulary lives in :mod:`backend.evidence.models` as a
# ``Literal`` rather than a SQL CHECK constraint — the set can grow
# without a migration and JSON storage is flexible.
disease_evidence_snapshots = Table(
    "disease_evidence_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column(
        "disease_slug",
        Text,
        ForeignKey("diseases.slug", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("taken_at", Text, nullable=False),
    Column("triggered_by_execution_id", Text),
    Column("triggered_by_flow_key", Text),
    Column("articles_seen_total", Integer, nullable=False, server_default="0"),
    Column(
        "articles_cited_in_guideline",
        Integer,
        nullable=False,
        server_default="0",
    ),
    Column("pmids_verified_ok", Integer, nullable=False, server_default="0"),
    Column("pmids_scrubbed", Integer, nullable=False, server_default="0"),
    Column("category_counts_json", Text, nullable=False, server_default="{}"),
    Column("quality_counts_json", Text, nullable=False, server_default="{}"),
    Column("knowledge_gaps_json", Text, nullable=False, server_default="[]"),
    Column("paragraphs_total", Integer, nullable=False, server_default="0"),
    Column(
        "paragraphs_passed_eval", Integer, nullable=False, server_default="0"
    ),
    Column("avg_synthesis_confidence", Float),
    Column("evidence_score", Integer, nullable=False, server_default="0"),
    Column("confidence_index", Integer, nullable=False, server_default="0"),
    Column("notes", Text, nullable=False, server_default=""),
)

# Primary read pattern — "latest N snapshots for this disease".
Index(
    "ix_disease_evidence_snapshots_disease_slug",
    disease_evidence_snapshots.c.disease_slug,
)
# Used by the admin trend chart that orders snapshots chronologically
# across all diseases.
Index(
    "ix_disease_evidence_snapshots_taken_at",
    disease_evidence_snapshots.c.taken_at,
)


article_category_audits = Table(
    "article_category_audits",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("pmid", Text, nullable=False),
    Column(
        "disease_slug",
        Text,
        ForeignKey("diseases.slug", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("triggered_by_execution_id", Text),
    Column("ai_categories_json", Text, nullable=False, server_default="[]"),
    Column("ai_rationale", Text, nullable=False, server_default=""),
    Column("ai_model", Text, nullable=False, server_default=""),
    Column("ai_confidence", Float),
    # Quality tier mirrors :mod:`backend.evidence_tiering` — one of
    # 'high' / 'moderate' / 'low' / 'very_low'. Nullable for audits
    # written before evidence tiering is computed (rare).
    Column("quality_tier", Text),
    Column("reviewer_categories_json", Text),
    Column("reviewer_id", Text),
    Column("reviewer_at", Text),
    Column("created_at", Text, nullable=False),
    # Natural key: a single workflow execution emits at most one audit
    # per (article, disease). Re-running the workflow generates a new
    # execution id and a new row, preserving the historical trail.
    UniqueConstraint(
        "pmid",
        "disease_slug",
        "triggered_by_execution_id",
        name="uq_article_category_audits_per_run",
    ),
    CheckConstraint(
        "quality_tier IS NULL OR quality_tier IN "
        "('high','moderate','low','very_low')",
        name="ck_article_category_audits_quality_tier",
    ),
)

# "Show me everything we know about this disease's evidence" — common
# admin dashboard query.
Index(
    "ix_article_category_audits_disease_slug",
    article_category_audits.c.disease_slug,
)
# "Show me every disease this PMID has been audited under" — supports
# the cross-disease article inspector view.
Index(
    "ix_article_category_audits_pmid",
    article_category_audits.c.pmid,
)


__all__ = [
    "metadata",
    "diseases",
    "guideline_documents",
    "catalog_stats",
    "content_prs",
    "care_pathways",
    "trials",
    "disease_trials",
    "therapies",
    "foundations",
    "disease_foundations",
    "private_contexts",
    "official_guideline_pointers",
    "disease_index",
    "disease_index_aliases",
    "disease_evidence_snapshots",
    "article_category_audits",
]
