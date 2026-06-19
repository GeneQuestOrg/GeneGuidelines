"""analyzed bibliography: papers the engine considered + verdict (researcher audit)

Revision ID: a2d6f4b1c9e7
Revises: f1a7c3e9b8d2
Create Date: 2026-06-17 22:30:00.000000

One table, ``guideline_analyzed_papers`` — the audit ledger of every paper the
shelf-build and monitor steps considered, with the engine's verdict
(shelf / suggestion / rejected / low) and the one-line reason. The negative paths
are the value (auditability + triage-quality dashboard). Snapshot of a run,
distinct from the live shelf / suggestions.

ORM-mapped against the shared ``MetaData`` in
``backend/guidelines/bibliography/orm.py``; generic types only (Text / Integer /
Float), valid on SQLite (tests) and Postgres (prod). Keyed on
``(disease_slug, step, ref)`` so the shelf and monitor runs each replace only
their own slice.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a2d6f4b1c9e7"
down_revision: Union[str, Sequence[str], None] = "f1a7c3e9b8d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "guideline_analyzed_papers",
        sa.Column("disease_slug", sa.Text(), nullable=False),
        sa.Column("step", sa.Text(), nullable=False),
        sa.Column("ref", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", sa.Text(), nullable=False),
        sa.Column("journal", sa.Text(), nullable=False),
        sa.Column("year", sa.Text(), nullable=False),
        sa.Column("access", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("pmid", sa.Text(), nullable=True),
        sa.Column("bookshelf", sa.Text(), nullable=True),
        sa.Column("change_probability", sa.Float(), nullable=True),
        sa.Column("suggestion_id", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "step IN ('shelf','monitor')",
            name=op.f("ck_guideline_analyzed_papers_guideline_analyzed_papers_step_enum"),
        ),
        sa.CheckConstraint(
            "verdict IN ('shelf','suggestion','rejected','low')",
            name=op.f("ck_guideline_analyzed_papers_guideline_analyzed_papers_verdict_enum"),
        ),
        sa.PrimaryKeyConstraint(
            "disease_slug", "step", "ref", name=op.f("pk_guideline_analyzed_papers")
        ),
    )
    op.create_index(
        "ix_guideline_analyzed_papers_disease_slug",
        "guideline_analyzed_papers",
        ["disease_slug"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_guideline_analyzed_papers_disease_slug",
        table_name="guideline_analyzed_papers",
    )
    op.drop_table("guideline_analyzed_papers")
