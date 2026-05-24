"""f8: evidence audit tables (snapshots + per-article categorisation)

Adds the two tables that back the F8 evidence audit dashboard:

- ``disease_evidence_snapshots`` — aggregate per-run snapshot of literature
  coverage, citation counts, category breakdown, quality / confidence
  scores. The series of snapshots for a disease forms a trendline.
- ``article_category_audits`` — per-article AI categorisation ledger.
  One row per (PMID, disease, execution_id); reviewer override columns
  reserved for the post-Auth0 milestone (F8 v0.3).

Both tables are pure additions — no existing tables are modified. The
migration mirrors the shapes declared in
:mod:`backend.shared.persistence.schema`. Production Postgres deployments
that already ran ``ensure_evidence_audit_schema`` from
:mod:`backend.evidence.repository` will have these tables already; the
``checkfirst`` behaviour in that helper keeps both paths idempotent.

Revision ID: c35847934df0
Revises: dd31c5539990
Create Date: 2026-05-24 22:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c35847934df0"
down_revision: Union[str, Sequence[str], None] = "dd31c5539990"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create snapshots + audits tables with their indexes."""
    op.create_table(
        "disease_evidence_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("disease_slug", sa.Text(), nullable=False),
        sa.Column("taken_at", sa.Text(), nullable=False),
        sa.Column("triggered_by_execution_id", sa.Text(), nullable=True),
        sa.Column("triggered_by_flow_key", sa.Text(), nullable=True),
        sa.Column(
            "articles_seen_total",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "articles_cited_in_guideline",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "pmids_verified_ok",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "pmids_scrubbed",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "category_counts_json",
            sa.Text(),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "quality_counts_json",
            sa.Text(),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "knowledge_gaps_json",
            sa.Text(),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "paragraphs_total",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "paragraphs_passed_eval",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("avg_synthesis_confidence", sa.Float(), nullable=True),
        sa.Column(
            "evidence_score",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "confidence_index",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.ForeignKeyConstraint(
            ["disease_slug"],
            ["diseases.slug"],
            name=op.f(
                "fk_disease_evidence_snapshots_disease_slug_diseases"
            ),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_disease_evidence_snapshots")
        ),
    )
    op.create_index(
        "ix_disease_evidence_snapshots_disease_slug",
        "disease_evidence_snapshots",
        ["disease_slug"],
        unique=False,
    )
    op.create_index(
        "ix_disease_evidence_snapshots_taken_at",
        "disease_evidence_snapshots",
        ["taken_at"],
        unique=False,
    )

    op.create_table(
        "article_category_audits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pmid", sa.Text(), nullable=False),
        sa.Column("disease_slug", sa.Text(), nullable=False),
        sa.Column("triggered_by_execution_id", sa.Text(), nullable=True),
        sa.Column(
            "ai_categories_json",
            sa.Text(),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "ai_rationale", sa.Text(), server_default="", nullable=False
        ),
        sa.Column("ai_model", sa.Text(), server_default="", nullable=False),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column("quality_tier", sa.Text(), nullable=True),
        sa.Column("reviewer_categories_json", sa.Text(), nullable=True),
        sa.Column("reviewer_id", sa.Text(), nullable=True),
        sa.Column("reviewer_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "quality_tier IS NULL OR quality_tier IN "
            "('high','moderate','low','very_low')",
            # ``op.f`` says "this is the fully conventionalized name"; the
            # convention prefixes ``ck_article_category_audits_`` so the
            # raw constraint fragment in schema.py is just ``quality_tier``.
            name=op.f("ck_article_category_audits_quality_tier"),
        ),
        sa.ForeignKeyConstraint(
            ["disease_slug"],
            ["diseases.slug"],
            name=op.f("fk_article_category_audits_disease_slug_diseases"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_article_category_audits")
        ),
        sa.UniqueConstraint(
            "pmid",
            "disease_slug",
            "triggered_by_execution_id",
            name=op.f("uq_article_category_audits_per_run"),
        ),
    )
    op.create_index(
        "ix_article_category_audits_disease_slug",
        "article_category_audits",
        ["disease_slug"],
        unique=False,
    )
    op.create_index(
        "ix_article_category_audits_pmid",
        "article_category_audits",
        ["pmid"],
        unique=False,
    )


def downgrade() -> None:
    """Drop snapshots + audits tables in reverse dependency order."""
    op.drop_index(
        "ix_article_category_audits_pmid",
        table_name="article_category_audits",
    )
    op.drop_index(
        "ix_article_category_audits_disease_slug",
        table_name="article_category_audits",
    )
    op.drop_table("article_category_audits")

    op.drop_index(
        "ix_disease_evidence_snapshots_taken_at",
        table_name="disease_evidence_snapshots",
    )
    op.drop_index(
        "ix_disease_evidence_snapshots_disease_slug",
        table_name="disease_evidence_snapshots",
    )
    op.drop_table("disease_evidence_snapshots")
