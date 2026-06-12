"""account domain: invites table (doctor onboarding tokens)

Revision ID: a1c4d9f2b3e8
Revises: feb15ef6e670
Create Date: 2026-06-12 12:00:00.000000

A signed-in parent (or superadmin) mints an invite for a doctor; the token
travels in a ``#/join/{token}`` URL. The accepting user, after signing in,
redeems it to take the ``doctor`` role (still unverified). One token = one use:
``used_by`` / ``used_at`` mark redemption, ``expires_at`` caps the lifetime.

Generic column types (Text/Integer) only, like the ``users`` migration, so the
same DDL is valid on both SQLite (offline alembic / Kaggle snapshot) and
Postgres (production). FKs reference ``users.id``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1c4d9f2b3e8"
down_revision: Union[str, Sequence[str], None] = "feb15ef6e670"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "invites",
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "intended_role",
            sa.Text(),
            server_default="doctor",
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("doctor_slug", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("used_by", sa.Text(), nullable=True),
        sa.Column("used_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "intended_role IN ('parent','doctor','researcher')",
            name=op.f("ck_invites_invite_role_enum"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_invites_created_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["used_by"],
            ["users.id"],
            name=op.f("fk_invites_used_by_users"),
        ),
        sa.PrimaryKeyConstraint("token", name=op.f("pk_invites")),
    )
    op.create_index(
        op.f("ix_invites_created_by"), "invites", ["created_by"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_invites_created_by"), table_name="invites")
    op.drop_table("invites")
