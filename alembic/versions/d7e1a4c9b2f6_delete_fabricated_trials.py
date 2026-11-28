"""delete two clinical trials that do not exist

Revision ID: d7e1a4c9b2f6
Revises: c3f9d2a7e5b1
Create Date: 2026-11-28 20:30:00.000000

The trials seed (backend/content_trials_seed.json) carried two invented studies, and production served them to parents as recruiting:

- NCT05998877, "GαS inhibitor pilot in McCune-Albright syndrome", with a named investigator at a real clinic and a contact e-mail address that was made up;
- NCT06334455, "MEK inhibitor in cardiovascular complications of Noonan syndrome", the same way; for Noonan syndrome it was the only recruiting trial behind the trials button on the parent map.

ClinicalTrials.gov answers 404 for both identifiers (checked 2026-11-28, together with the other 50 trials in production, which all exist). The seed no longer contains them, but the loader only inserts missing rows, so removing a seed entry does not remove a row an earlier deploy wrote. This migration removes the rows.

Deploy order: ship the code first (so the seed cannot put them back at the next start), then run this migration. Not reversible on purpose: downgrade is a no-op.

Deploy note: ``export DB_URL`` before ``alembic upgrade head``.
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7e1a4c9b2f6"
down_revision: Union[str, None] = "c3f9d2a7e5b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FABRICATED_NCTS = ("NCT05998877", "NCT06334455")


def _has(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    for table in ("disease_trials", "trials"):
        if _has(table):
            bind.execute(sa.text(f"DELETE FROM {table} WHERE nct IN :ncts").bindparams(sa.bindparam("ncts", expanding=True)), {"ncts": list(FABRICATED_NCTS)})


def downgrade() -> None:
    """Nothing to restore: the rows described studies that do not exist."""
