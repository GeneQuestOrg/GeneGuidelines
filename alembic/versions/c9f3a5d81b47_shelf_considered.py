"""guideline_shelf_considered — record why a candidate was left off the shelf

Revision ID: c9f3a5d81b47
Revises: b2e7d419c8a5
Create Date: 2026-09-04 12:00:00.000000

The shelf classifier has always been asked to return `considered` — every candidate
it rejected, with a reason and a category — and nothing ever stored it. So every
rejection was invisible, and the shelf silently lost good documents on separate
runs (the paediatric review, the 2012 craniofacial guidelines, then the 2023 NIH
craniofacial review). Each time a human only noticed by reading the synthesis
afterwards and wondering what had happened.

This table holds the latest run's rejections per disease, which is what the
question "why is this not on the shelf right now?" actually needs. It is replaced
per disease on each rebuild rather than appended, so it stays a snapshot, not a log.

Deploy note: ``export DB_URL`` before ``alembic upgrade head``. Create the table
BEFORE deploying the code that writes it — the reverse order took the source-shelf
endpoint down for fifteen minutes on 2026-09-03.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9f3a5d81b47"
down_revision: Union[str, None] = "b2e7d419c8a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "guideline_shelf_considered"


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("disease_slug", sa.Text(), nullable=False),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.Text(), nullable=False, server_default=""),
        sa.Column("considered_at", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("disease_slug", "doc_id"),
    )
    op.create_index(
        "ix_guideline_shelf_considered_disease_slug", _TABLE, ["disease_slug"]
    )


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table(_TABLE):
        return
    op.drop_index("ix_guideline_shelf_considered_disease_slug", table_name=_TABLE)
    op.drop_table(_TABLE)
