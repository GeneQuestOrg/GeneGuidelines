"""therapies_pmids_json_column

Revision ID: 19c5c5f78294
Revises: e5a3c1f7d2b9
Create Date: 2026-06-19 09:51:20.814742

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19c5c5f78294'
down_revision: Union[str, Sequence[str], None] = 'e5a3c1f7d2b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('therapies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pmids_json', sa.Text(), server_default='[]', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('therapies', schema=None) as batch_op:
        batch_op.drop_column('pmids_json')
