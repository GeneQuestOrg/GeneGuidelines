"""account domain: users table (Auth0 identity + app-side role/verification)

Revision ID: feb15ef6e670
Revises: dd31c5539990
Create Date: 2026-06-12 00:00:00.000000

The ``users`` table holds every authenticated principal. Auth0 is the identity
provider only; role / verification / ORCID / institution live here (see
docs/adr/003). Generic column types (Text/Integer) keep the migration valid on
both SQLite (offline alembic / Kaggle snapshot) and Postgres (production).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "feb15ef6e670"
down_revision: Union[str, Sequence[str], None] = "dd31c5539990"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("auth0_sub", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("verified", sa.Integer(), server_default="0", nullable=False),
        sa.Column("orcid", sa.Text(), nullable=True),
        sa.Column("institution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("last_login_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "role IS NULL OR role IN "
            "('parent','doctor','researcher','superadmin')",
            name=op.f("ck_users_user_role_enum"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("auth0_sub", name=op.f("uq_users_auth0_sub")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
