"""research_queue domain: research_jobs durable admission queue (RES-2)

Revision ID: b4f8a1c2d9e3
Revises: c7e2a9f4d6b1
Create Date: 2026-06-12 20:00:00.000000

Durable backing store for the fair-share research admission queue. RES-1 held
the queue in an in-process ``asyncio.PriorityQueue`` that a restart or worker
crash dropped; this table makes queued/running jobs survive both. The worker
claims one row at a time with ``SELECT ... FOR UPDATE SKIP LOCKED`` and a
stale-lock reaper requeues abandoned jobs (Solid Queue / Oban style — no
Celery, no broker).

Semantics match RES-1: ``priority`` is the JobClass int (0 = authenticated,
1 = anonymous; lower served first), FIFO within a class via ``created_at``;
the anon cap counts unfinished (queued OR running) rows per ``anon_session``.

Generic column types (Text/Integer) only, like the ``users``/``invites``
migrations, so the same DDL is valid on both SQLite (offline alembic / Kaggle
snapshot) and Postgres (production).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4f8a1c2d9e3"
down_revision: Union[str, Sequence[str], None] = "c7e2a9f4d6b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "research_jobs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("execution_id", sa.Text(), nullable=False),
        sa.Column(
            "payload_json", sa.Text(), server_default="{}", nullable=False
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.Text(), server_default="queued", nullable=False
        ),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("anon_session", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_at", sa.Text(), nullable=True),
        sa.Column("locked_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','running','done','failed')",
            name=op.f("ck_research_jobs_research_job_status_enum"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_research_jobs")),
    )
    op.create_index(
        "ix_research_jobs_claim",
        "research_jobs",
        ["status", "priority", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_research_jobs_anon_session",
        "research_jobs",
        ["anon_session", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_research_jobs_anon_session", table_name="research_jobs")
    op.drop_index("ix_research_jobs_claim", table_name="research_jobs")
    op.drop_table("research_jobs")
