"""guideline suggestion votes: per-clinician rating of an AI suggestion (SIG-1)

Revision ID: d7b2e9c14a06
Revises: c9d4e2f1a7b3
Create Date: 2026-06-22 00:00:00.000000

One table, ``guideline_suggestion_votes`` — the write loop behind the rail's
3-state rating (useful / not / wrong). One row per (disease, suggestion, user);
re-rating upserts, the same verdict twice clears it. The aggregate counts on
``guideline_suggestions.signal`` are recomputed from these rows on every write,
so the tally only ever reflects real votes (no fabricated numbers).

ORM-mapped against the shared ``MetaData`` in ``backend/guidelines/orm.py``;
generic types only (Text / Integer), valid on SQLite (tests) and Postgres (prod).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d7b2e9c14a06"
down_revision: Union[str, Sequence[str], None] = "c9d4e2f1a7b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "guideline_suggestion_votes",
        sa.Column("disease_slug", sa.Text(), nullable=False),
        sa.Column("suggestion_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("verified_vote", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "verdict IN ('useful','not','wrong')",
            name=op.f(
                "ck_guideline_suggestion_votes_guideline_suggestion_vote_verdict_enum"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "disease_slug",
            "suggestion_id",
            "user_id",
            name=op.f("pk_guideline_suggestion_votes"),
        ),
    )
    op.create_index(
        "ix_guideline_suggestion_votes_suggestion",
        "guideline_suggestion_votes",
        ["disease_slug", "suggestion_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_guideline_suggestion_votes_suggestion",
        table_name="guideline_suggestion_votes",
    )
    op.drop_table("guideline_suggestion_votes")
