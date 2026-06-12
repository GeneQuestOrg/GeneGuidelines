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
    # Public-catalog visibility (RES-1, unlisted-until-approve). Existing rows
    # default to 1 (visible — zero regression); bootstrap inserts new diseases
    # with 0 so they appear only via direct link until a superadmin approves.
    # Distinct from ``status`` (epistemic state) — this is purely visibility.
    Column("listed", Integer, nullable=False, server_default="1"),
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


# -- account domain -----------------------------------------------------------
#
# Authenticated users. Auth0 is *only* the identity provider (issues the JWT);
# everything the app reasons about — role, verification status, ORCID,
# institution — lives here, in our database, not in IdP metadata. See
# ``docs/adr/003-auth0-eu-idp-and-account-model.md``.
#
# A row is created just-in-time on the first request carrying a valid JWT
# (``auth0_sub`` is the stable Auth0 subject claim). ``role`` is ``NULL`` until
# the user picks one (parent/doctor/researcher) — the frontend forces that
# one-time choice. ``verified`` gates doctor identity (AUTH-4 / D5).
#
# Generic column types only (Text/Integer): the same migration applies on both
# SQLite (Kaggle snapshot / offline alembic) and Postgres (production engine).
users = Table(
    "users",
    metadata,
    Column("id", Text, primary_key=True),  # uuid4 hex
    Column("auth0_sub", Text, nullable=False, unique=True),
    Column("email", Text, nullable=False),
    Column("display_name", Text),
    Column("role", Text),  # NULL until the user picks parent/doctor/researcher
    Column("verified", Integer, nullable=False, server_default="0"),
    Column("orcid", Text),
    Column("institution", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("last_login_at", Text),
    CheckConstraint(
        "role IS NULL OR role IN "
        "('parent','doctor','researcher','superadmin')",
        name="user_role_enum",
    ),
)

# Lookups by email back the admin Users view and superadmin bootstrap.
Index("ix_users_email", users.c.email)


# Doctor onboarding invites (AUTH-4). A signed-in parent (or superadmin) mints a
# token; it travels in a ``#/join/{token}`` URL. The accepting user redeems it
# to take the ``doctor`` role (still unverified). One token = one redemption:
# ``used_by`` / ``used_at`` mark it spent, ``expires_at`` caps its lifetime.
# ``doctor_slug`` records which doctor profile the parent meant to invite (UI
# context only — no FK, the catalogue is not in this metadata yet).
invites = Table(
    "invites",
    metadata,
    Column("token", Text, primary_key=True),  # secrets.token_urlsafe(32)
    Column("created_by", Text, ForeignKey("users.id"), nullable=False),
    Column("intended_role", Text, nullable=False, server_default="doctor"),
    Column("email", Text),
    Column("doctor_slug", Text),
    Column("created_at", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
    Column("used_by", Text, ForeignKey("users.id")),
    Column("used_at", Text),
    CheckConstraint(
        "intended_role IN ('parent','doctor','researcher')",
        name="invite_role_enum",
    ),
)

# The parent's "invites I created" lookups and the admin overview hit this.
Index("ix_invites_created_by", invites.c.created_by)


# -- research_queue domain ----------------------------------------------------
#
# Durable fair-share admission queue for disease-bootstrap fan-outs (RES-2).
# RES-1 kept this in an in-process ``asyncio.PriorityQueue`` that a backend
# restart or worker crash silently dropped. This table is the durable backing
# store: rows survive restarts, the worker claims one row at a time with
# ``SELECT ... FOR UPDATE SKIP LOCKED`` (Solid Queue / Oban style — no Celery,
# no broker), and a stale-lock reaper requeues jobs an exited worker abandoned.
#
# Semantics are unchanged from RES-1: ``priority`` is the integer JobClass
# (0 = authenticated, 1 = anonymous; lower served first), and FIFO within a
# class falls out of ordering by ``created_at`` next. The anon cap counts
# unfinished rows (queued OR running) for an ``anon_session`` bucket.
#
# Generic column types only (Text/Integer): the same DDL is valid on both
# SQLite (offline alembic / Kaggle snapshot) and Postgres (production engine).
# ``created_at`` / ``locked_at`` are ISO-8601 strings like every other
# timestamp column in this schema (Text), so ordering is lexicographic and
# portable.
research_jobs = Table(
    "research_jobs",
    metadata,
    Column("id", Text, primary_key=True),  # uuid4 hex
    Column("execution_id", Text, nullable=False),  # gl-… run id the FE polls
    Column("payload_json", Text, nullable=False, server_default="{}"),
    Column("priority", Integer, nullable=False),  # JobClass int (0 auth, 1 anon)
    Column("status", Text, nullable=False, server_default="queued"),
    Column("user_id", Text),  # NULL for anonymous callers
    Column("anon_session", Text),  # NULL for authenticated callers
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("locked_at", Text),  # ISO-8601 when a worker claimed it
    Column("locked_by", Text),  # worker id holding the claim
    Column("created_at", Text, nullable=False),
    Column("started_at", Text),
    Column("finished_at", Text),
    Column("error", Text),
    CheckConstraint(
        "status IN ('queued','running','done','failed')",
        name="research_job_status_enum",
    ),
)

# Claiming hot path: ``WHERE status='queued' ORDER BY priority, created_at``.
Index(
    "ix_research_jobs_claim",
    research_jobs.c.status,
    research_jobs.c.priority,
    research_jobs.c.created_at,
)
# Anonymous-cap lookup: unfinished rows per session bucket.
Index(
    "ix_research_jobs_anon_session",
    research_jobs.c.anon_session,
    research_jobs.c.status,
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
    "users",
    "invites",
    "research_jobs",
]
