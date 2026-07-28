"""therapies.pmids_json column (per-therapy PubMed provenance)

Revision ID: 19c5c5f78294
Revises: e2f9a1c7b4d3
Create Date: 2026-07-28 10:00:00.000000

Adds a JSON-array-of-PMID provenance column to ``therapies``. The
therapies_finder populates it during research; the serve boundary
(``backend/content/contracts.py``) uses PMID-presence to decide whether a row
is shown as honestly "source-backed" or the neutral "unverified" default.

Existing rows default to ``'[]'`` (no source on file yet → they keep serving
"unverified" until the finder repopulates or a backfill runs), so the NOT NULL
add succeeds on a populated table.

Generic column type (Text) with a server default so the same DDL is valid on
both SQLite (offline alembic) and Postgres (production). ``render_as_batch`` is
enabled in env.py; a plain ADD COLUMN is a no-op under batch mode on Postgres.

Deploy note: ``export DB_URL`` before ``alembic upgrade head``.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "19c5c5f78294"
down_revision: Union[str, Sequence[str], None] = "e2f9a1c7b4d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "therapies",
        sa.Column(
            "pmids_json",
            sa.Text(),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("therapies", "pmids_json")
