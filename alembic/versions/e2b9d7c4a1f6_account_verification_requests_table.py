"""account domain: verification_requests table (self-serve manual verification)

Revision ID: e2b9d7c4a1f6
Revises: c1b7a4e8f0d2
Create Date: 2026-07-09 10:00:00.000000

A doctor or researcher who cannot (or prefers not to) auto-verify via an ORCID
link submits identity evidence — an ORCID iD, a professional licence number, an
institution, and/or a free-text note — for a superadmin to review. Approval
flips ``users.verified`` to true (the same code path a superadmin uses in the
Users view); rejection records the decision and leaves the account unverified.
ORCID auto-verify never touches this table — it sets ``verified`` directly.

Generic column types (Text) only, like the ``users`` / ``invites`` migrations,
so the same DDL is valid on both SQLite (offline alembic / Kaggle snapshot) and
Postgres (production). FKs reference ``users.id``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2b9d7c4a1f6"
down_revision: Union[str, Sequence[str], None] = "c1b7a4e8f0d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "verification_requests",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("orcid", sa.Text(), nullable=True),
        sa.Column("license_no", sa.Text(), nullable=True),
        sa.Column("institution", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "role IN ('doctor','researcher')",
            name=op.f("ck_verification_requests_verification_request_role_enum"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name=op.f("ck_verification_requests_verification_request_status_enum"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_verification_requests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_verification_requests_reviewed_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_requests")),
    )
    op.create_index(
        op.f("ix_verification_requests_status"),
        "verification_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_verification_requests_user_id"),
        "verification_requests",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_verification_requests_user_id"),
        table_name="verification_requests",
    )
    op.drop_index(
        op.f("ix_verification_requests_status"),
        table_name="verification_requests",
    )
    op.drop_table("verification_requests")
