"""content domain: diseases.listed column (RES-1, unlisted-until-approve)

Revision ID: c7e2a9f4d6b1
Revises: a1c4d9f2b3e8
Create Date: 2026-06-12 18:00:00.000000

Public-catalog visibility flag, distinct from the existing ``status`` column
(epistemic state — ai-draft/draft/review/published). Existing rows default to
1 (visible — zero regression); the public ``POST /bootstrap-disease`` endpoint
inserts new diseases with 0 so they appear only via direct link until a
superadmin approves them.

Generic column type (Integer) with a server default so the same DDL is valid on
both SQLite (offline alembic / Kaggle snapshot) and Postgres (production), and
so the ``NOT NULL`` add succeeds on a populated table.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e2a9f4d6b1"
down_revision: Union[str, Sequence[str], None] = "a1c4d9f2b3e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "diseases",
        sa.Column(
            "listed",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("diseases", "listed")
