"""guideline_points: the generated "What the guideline says about diagnosis" block per disease

Revision ID: c3f9d2a7e5b1
Revises: b5e8a1c3d9f2
Create Date: 2026-11-24 00:00:00.000000

One row per disease, written by the guideline-points job (``backend.services.guideline_points_job``) after a synthesis, or by the admin backfill. ``publish`` = 0 rows are kept so an unchanged shelf is not paid for twice, and are never served. FD has no row: its page keeps the hand-written block.

Deploy note: ``export DB_URL`` before ``alembic upgrade head``.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "c3f9d2a7e5b1"
down_revision: Union[str, None] = "b5e8a1c3d9f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("guideline_points"):
        return
    op.create_table(
        "guideline_points",
        sa.Column("disease_slug", sa.Text(), primary_key=True),
        sa.Column("publish", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("shelf_hash", sa.Text(), nullable=False),
        sa.Column("block", sa.JSON(), nullable=True),
        sa.Column("record", sa.JSON(), nullable=False),
        sa.Column("models", sa.Text(), nullable=False, server_default=""),
        sa.Column("cost_usd", sa.Text(), nullable=False, server_default=""),
        sa.Column("generated_at", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("guideline_points")
