"""private_contexts.user_id — tie uploads to parent accounts

Revision ID: c9d4e2f1a7b3
Revises: b8e3f1a2c4d5
Create Date: 2026-06-21 18:00:00.000000

My case uploads are parent-only when Auth0 is enabled. Existing rows keep
user_id NULL (anonymous legacy uploads from before the gate).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d4e2f1a7b3"
down_revision: Union[str, Sequence[str], None] = "b8e3f1a2c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("private_contexts", sa.Column("user_id", sa.Text(), nullable=True))
    op.create_index(
        "ix_private_contexts_disease_user",
        "private_contexts",
        ["disease_slug", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_private_contexts_disease_user", table_name="private_contexts")
    op.drop_column("private_contexts", "user_id")
