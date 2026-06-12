"""doctor_contributions domain: doctor_submissions + parent_recs (DOC-5)

Revision ID: e5a3c1f7d2b9
Revises: b4f8a1c2d9e3
Create Date: 2026-06-12 21:30:00.000000

The parent write-path for the doctor directory (DOC-5). A signed-in parent can
propose a clinician we are missing (``doctor_submissions``) and leave a
recommendation for a doctor (``parent_recs``); both start ``review_status =
pending`` and only become public once a superadmin approves them. RODO
provenance on a submission follows ADR 009 (inform, don't ask consent): the
courtesy email is sent manually for now and ``rodo_email_sent_at`` records it.

This is the first ORM-mapped domain; the tables are declared as mapped
dataclasses against the *same* ``MetaData`` as the Core schema, so this DDL
matches ``backend/doctor_contributions/orm.py`` exactly.

Generic column types (Text/Integer) only and ISO-8601 string timestamps (like
``research_jobs``), so the same DDL is valid on SQLite (offline alembic / tests)
and Postgres (production).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5a3c1f7d2b9"
down_revision: Union[str, Sequence[str], None] = "b4f8a1c2d9e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "doctor_submissions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("submitted_by", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("specialty", sa.Text(), nullable=False),
        sa.Column("institution", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("disease_slug", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("possible_duplicate", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False),
        sa.Column("rodo_status", sa.Text(), nullable=False),
        sa.Column("rodo_contact_email", sa.Text(), nullable=True),
        sa.Column("rodo_email_sent_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name=op.f("ck_doctor_submissions_doctor_submission_review_status_enum"),
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"],
            ["users.id"],
            name=op.f("fk_doctor_submissions_submitted_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_doctor_submissions_reviewed_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_doctor_submissions")),
    )
    op.create_index(
        "ix_doctor_submissions_review_status",
        "doctor_submissions",
        ["review_status"],
        unique=False,
    )

    op.create_table(
        "parent_recs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("doctor_slug", sa.Text(), nullable=False),
        sa.Column("submitted_by", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("relation", sa.Text(), nullable=False),
        sa.Column("review_status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "review_status IN ('pending','approved','rejected')",
            name=op.f("ck_parent_recs_parent_rec_review_status_enum"),
        ),
        sa.CheckConstraint(
            "relation IN ('parent','carer')",
            name=op.f("ck_parent_recs_parent_rec_relation_enum"),
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by"],
            ["users.id"],
            name=op.f("fk_parent_recs_submitted_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_parent_recs_reviewed_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parent_recs")),
    )
    op.create_index(
        "ix_parent_recs_doctor_slug",
        "parent_recs",
        ["doctor_slug", "review_status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_parent_recs_doctor_slug", table_name="parent_recs")
    op.drop_table("parent_recs")
    op.drop_index(
        "ix_doctor_submissions_review_status", table_name="doctor_submissions"
    )
    op.drop_table("doctor_submissions")
