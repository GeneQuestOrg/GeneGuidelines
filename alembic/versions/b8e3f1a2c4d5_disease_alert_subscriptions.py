"""disease alert subscriptions (double opt-in email)

Revision ID: b8e3f1a2c4d5
Revises: a2d6f4b1c9e7
Create Date: 2026-06-21 12:00:00.000000

Families subscribe to substantive updates for a disease slug. Status flow:
pending -> confirmed (via email link) or unsubscribed. Generic Text types for
SQLite test compatibility and Postgres production.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e3f1a2c4d5"
down_revision: Union[str, Sequence[str], None] = "a2d6f4b1c9e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "disease_alert_subscriptions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("disease_slug", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("confirm_token", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("prefs_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("radius_km", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.Text(), nullable=True),
        sa.Column("unsubscribed_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending','confirmed','unsubscribed')",
            name=op.f("ck_disease_alert_subscriptions_status_enum"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_disease_alert_subscriptions")),
        sa.UniqueConstraint(
            "confirm_token",
            name=op.f("uq_disease_alert_subscriptions_confirm_token"),
        ),
        sa.UniqueConstraint(
            "disease_slug",
            "email",
            name=op.f("uq_disease_alert_subscriptions_slug_email"),
        ),
    )
    op.create_index(
        op.f("ix_disease_alert_subscriptions_disease_slug"),
        "disease_alert_subscriptions",
        ["disease_slug"],
        unique=False,
    )
    op.create_index(
        op.f("ix_disease_alert_subscriptions_email"),
        "disease_alert_subscriptions",
        ["email"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_disease_alert_subscriptions_email"),
        table_name="disease_alert_subscriptions",
    )
    op.drop_index(
        op.f("ix_disease_alert_subscriptions_disease_slug"),
        table_name="disease_alert_subscriptions",
    )
    op.drop_table("disease_alert_subscriptions")
