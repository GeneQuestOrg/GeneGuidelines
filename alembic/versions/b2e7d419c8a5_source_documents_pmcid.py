"""guideline_source_documents.pmcid — link the shelf to open-access full text

Revision ID: b2e7d419c8a5
Revises: f4c8d1b6a903
Create Date: 2026-09-03 10:00:00.000000

The source shelf linked every document to its PubMed abstract page, even when the
whole article is free to read in PMC. A parent who wants to check what the guideline
actually says had to land on an abstract and find their own way to the full text —
and for the FD/MAS consensus the abstract is the one part that does not mention
biopsy, imaging or histopathology at all.

This column stores the PMC id resolved during the shelf run (NCBI elink,
``linkname=pubmed_pmc``), so the shelf card can point straight at the readable
article. Nullable: closed-access documents and Bookshelf entries have none and keep
linking to PubMed as before.

Generic Text with no server default so the same DDL is valid on SQLite (offline
alembic) and PostgreSQL (production); ``render_as_batch`` is enabled in env.py.

Deploy note: ``export DB_URL`` before ``alembic upgrade head``. Existing rows get
NULL and are backfilled by the next shelf run for that disease — no data migration
needed, and nothing breaks in the meantime.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2e7d419c8a5"
down_revision: Union[str, None] = "f4c8d1b6a903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "guideline_source_documents"
_COLUMN = "pmcid"


def _has_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return True  # nothing to add; treat as done
    return any(c["name"] == _COLUMN for c in inspector.get_columns(_TABLE))


def upgrade() -> None:
    if _has_column():
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    if any(c["name"] == _COLUMN for c in inspector.get_columns(_TABLE)):
        op.drop_column(_TABLE, _COLUMN)
