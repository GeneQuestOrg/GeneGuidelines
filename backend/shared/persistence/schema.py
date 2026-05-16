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
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
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
        primary_key=True,
    ),
    Column("locale", Text, nullable=False, server_default="en"),
    Column("version", Text, nullable=False),
    Column("based_on", Text, nullable=False),
    Column("generated_at", Text, nullable=False),
    Column("source_guideline_version", Text),
    Column("source_execution_id", Text),
    Column("tree_json", Text, nullable=False),
    Column("draft_tree_json", Text),
    Column("draft_updated_at", Text),
)


__all__ = [
    "metadata",
    "diseases",
    "guideline_documents",
    "catalog_stats",
    "content_prs",
    "care_pathways",
]
