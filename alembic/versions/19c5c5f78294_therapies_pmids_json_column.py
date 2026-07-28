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


def _therapies_columns() -> set[str]:
    insp = sa.inspect(op.get_bind())
    if "therapies" not in insp.get_table_names():
        return set()  # table absent: created by content_db.ensure_content_schema, not alembic
    return {c["name"] for c in insp.get_columns("therapies")}


def upgrade() -> None:
    """Upgrade schema.

    ``therapies`` is created by ``content_db.ensure_content_schema`` (raw
    psycopg), not by alembic, so a pure-alembic chain (offline SQLite, the
    migration-roundtrip test) has no such table. Guard the ADD so the migration
    is a no-op where the table is absent, and idempotent where the column
    already exists.
    """
    cols = _therapies_columns()
    if not cols or "pmids_json" in cols:
        return
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
    """Downgrade schema (guarded symmetrically)."""
    cols = _therapies_columns()
    if "pmids_json" not in cols:
        return
    op.drop_column("therapies", "pmids_json")
