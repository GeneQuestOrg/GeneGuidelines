"""guidelines layer: source docs + synthesis + suggestions + signals (GL-4)

Revision ID: f1a7c3e9b8d2
Revises: e5a3c1f7d2b9
Create Date: 2026-06-16 21:45:00.000000

The read side of draft10's guidelines layer (D6): a disease's curated source
shelf (``guideline_source_documents``), the ONE AI synthesis over it
(``guideline_synthesis``), the suggestions hanging alongside as deltas
(``guideline_suggestions``), and the asymmetric per-section signal
(``guideline_synthesis_signals``).

ORM-mapped domain — these tables are declared as mapped dataclasses against the
shared ``MetaData`` in ``backend/guidelines/orm.py``, so this DDL matches it
exactly. Generic types only (Text / Integer / JSON), valid on SQLite (tests /
offline alembic) and Postgres (production). Nested document fields use ``JSON``
(JSONB on Postgres, JSON-as-text on SQLite).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a7c3e9b8d2"
down_revision: Union[str, Sequence[str], None] = "e5a3c1f7d2b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "guideline_source_documents",
        sa.Column("disease_slug", sa.Text(), nullable=False),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", sa.Text(), nullable=False),
        sa.Column("journal", sa.Text(), nullable=False),
        sa.Column("year", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("covers", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("pmid", sa.Text(), nullable=True),
        sa.Column("bookshelf", sa.Text(), nullable=True),
        sa.Column("free_full_text", sa.Integer(), nullable=False),
        sa.Column("is_new", sa.Integer(), nullable=False),
        sa.Column("updates_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "disease_slug", "doc_id", name=op.f("pk_guideline_source_documents")
        ),
    )
    op.create_index(
        "ix_guideline_source_documents_disease_slug",
        "guideline_source_documents",
        ["disease_slug"],
        unique=False,
    )

    op.create_table(
        "guideline_synthesis",
        sa.Column("disease_slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("last_updated", sa.Text(), nullable=False),
        sa.Column("based_on", sa.Text(), nullable=False),
        sa.Column("synth_disclaimer", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("epistemic_level", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("has_flowchart", sa.Integer(), nullable=False),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("what_to_do_now", sa.JSON(), nullable=True),
        sa.Column("red_flags", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "epistemic_level IN ('a','b','c')",
            name=op.f("ck_guideline_synthesis_guideline_synthesis_epistemic_level_enum"),
        ),
        sa.PrimaryKeyConstraint("disease_slug", name=op.f("pk_guideline_synthesis")),
    )

    op.create_table(
        "guideline_suggestions",
        sa.Column("disease_slug", sa.Text(), nullable=False),
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("target_section", sa.Text(), nullable=False),
        sa.Column("section_label", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("gate", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("signal", sa.JSON(), nullable=False),
        sa.Column("comments", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("parent_text", sa.Text(), nullable=True),
        sa.Column("diff", sa.JSON(), nullable=True),
        sa.Column("regen_seed", sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('addition','modification')",
            name=op.f("ck_guideline_suggestions_guideline_suggestion_kind_enum"),
        ),
        sa.CheckConstraint(
            "gate IN ('promoted','expert')",
            name=op.f("ck_guideline_suggestions_guideline_suggestion_gate_enum"),
        ),
        sa.PrimaryKeyConstraint(
            "disease_slug", "id", name=op.f("pk_guideline_suggestions")
        ),
    )
    op.create_index(
        "ix_guideline_suggestions_disease_slug",
        "guideline_suggestions",
        ["disease_slug"],
        unique=False,
    )

    op.create_table(
        "guideline_synthesis_signals",
        sa.Column("disease_slug", sa.Text(), nullable=False),
        sa.Column("section_id", sa.Text(), nullable=False),
        sa.Column("up", sa.Integer(), nullable=False),
        sa.Column("flags", sa.Integer(), nullable=False),
        sa.Column("verified", sa.Integer(), nullable=False),
        sa.Column("flag_notes", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint(
            "disease_slug", "section_id", name=op.f("pk_guideline_synthesis_signals")
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("guideline_synthesis_signals")
    op.drop_index(
        "ix_guideline_suggestions_disease_slug", table_name="guideline_suggestions"
    )
    op.drop_table("guideline_suggestions")
    op.drop_table("guideline_synthesis")
    op.drop_index(
        "ix_guideline_source_documents_disease_slug",
        table_name="guideline_source_documents",
    )
    op.drop_table("guideline_source_documents")
