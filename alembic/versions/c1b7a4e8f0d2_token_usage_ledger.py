"""token_usage ledger (research worker token-budget guard)

Revision ID: c1b7a4e8f0d2
Revises: d7b2e9c14a06
Create Date: 2026-06-24 16:00:00.000000

Greenfield per-LLM-call token-usage ledger. The dedicated research worker (and
local single-process dev) appends one row per successful LLM call so the budget
guard can SUM spend for the current billing window and stop claiming new disease
jobs once the monthly cap (``RESEARCH_TOKEN_BUDGET_MONTHLY``) is reached.

Generic column types (Text/Integer) only, like the ``research_jobs`` /
``users`` migrations, so the same DDL is valid on both SQLite (offline alembic /
tests) and Postgres (production). ``window_key`` is the SUM bucket (``YYYY-MM``
for monthly).

Deploy note: ``export DB_URL`` before ``alembic upgrade head`` (the engine reads
``DB_URL`` from the environment).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1b7a4e8f0d2"
down_revision: Union[str, Sequence[str], None] = "d7b2e9c14a06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "token_usage",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("execution_id", sa.Text(), nullable=False),
        sa.Column("disease_slug", sa.Text(), nullable=True),
        sa.Column("model_spec", sa.Text(), nullable=False),
        sa.Column(
            "prompt_tokens", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "completion_tokens", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "total_tokens", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("window_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_token_usage")),
    )
    op.create_index(
        "ix_token_usage_window_key",
        "token_usage",
        ["window_key"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_token_usage_window_key", table_name="token_usage")
    op.drop_table("token_usage")
