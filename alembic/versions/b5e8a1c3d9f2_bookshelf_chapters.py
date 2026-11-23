"""bookshelf_chapters: GeneReviews chapter text read from NCBI's bulk archive

Revision ID: b5e8a1c3d9f2
Revises: a7d2c9e4f1b3
Create Date: 2026-11-23 23:00:00.000000

NCBI Bookshelf answers automated requests for chapter pages with a reCAPTCHA page, so no GeneReviews chapter on any shelf has contributed text to a synthesis. Chapters are now read from NCBI's Literature Archive (``gene_NBK1116.tar.gz``) by a periodic job and stored here (``backend.services.genereviews_refresh``); ``backend.tools.bookshelf_fulltext`` reads this table before it tries the web page.

The table starts empty. Fill it with ``python -m backend.services.genereviews_refresh`` (or the admin endpoint ``POST /api/pipeline/genereviews/refresh``); the worker also refreshes it once a day when a shelf needs a chapter it does not hold, and once a week otherwise.

Deploy note: ``export DB_URL`` before ``alembic upgrade head``.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "b5e8a1c3d9f2"
down_revision: Union[str, None] = "a7d2c9e4f1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("bookshelf_chapters"):
        return
    op.create_table(
        "bookshelf_chapters",
        sa.Column("accession", sa.Text(), primary_key=True),
        sa.Column("book", sa.Text(), nullable=False),
        sa.Column("shortname", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("licence", sa.Text(), nullable=False, server_default=""),
        sa.Column("copyright", sa.Text(), nullable=False, server_default=""),
        sa.Column("synonyms", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_last_modified", sa.Text(), nullable=False, server_default=""),
        sa.Column("fetched_at", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("bookshelf_chapters")
