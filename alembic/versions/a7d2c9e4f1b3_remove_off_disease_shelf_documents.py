"""remove shelf documents that are about another disease

Revision ID: a7d2c9e4f1b3
Revises: d3a71f5c2e88
Create Date: 2026-11-23 22:00:00.000000

The shelf of "Severe growth deficiency-strabismus-extensive dermal melanocytosis-intellectual disability syndrome" (PUS3, OMIM 617051) held two GeneReviews chapters on other diseases, both stored under the section title "Clinical Characteristics":

- NBK601394, Schinzel-Giedion Syndrome (SETBP1; OMIM 269150);
- NBK621299, PTDSS1-Related Lenz-Majewski Hyperostotic Dysplasia (PTDSS1; OMIM 151050).

The Bookshelf search had matched section records that mention PUS3 in passing. The shelf builder now rejects such hits (``backend/guidelines/relevance.py``), but a fixed builder does not delete rows an earlier run wrote, and the shelf writer would otherwise carry them forward. Checked on 2026-11-23 against every catalog shelf from the public API (title, PubMed abstract, open-access full text, NCBI's GeneReviews index): these two are the only documents about another disease.

Each removal is recorded in ``guideline_shelf_considered`` as "off-topic", so the shelf's audit trail says why it is gone. The disease is left with an empty shelf, which is the honest state: the page already shows "no agreed guideline", and the synthesis stays withheld (ADR 005).

Not reversible: putting another disease's chapter back on this shelf is never wanted. Downgrade is a no-op on purpose.

Deploy note: ``export DB_URL`` before ``alembic upgrade head``.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "a7d2c9e4f1b3"
down_revision: Union[str, None] = "d3a71f5c2e88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SLUG = "severe-growth-deficiency-strabismus-extensive-dermal-melanocytos"
_OFF_DISEASE = {
    "NBK601394": ("Schinzel-Giedion Syndrome", "About another disease: GeneReviews chapter on Schinzel-Giedion syndrome (SETBP1, OMIM 269150), not PUS3 / OMIM 617051."),
    "NBK621299": ("PTDSS1-Related Lenz-Majewski Hyperostotic Dysplasia", "About another disease: GeneReviews chapter on Lenz-Majewski hyperostotic dysplasia (PTDSS1, OMIM 151050), not PUS3 / OMIM 617051."),
}


def _has(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has("guideline_source_documents"):
        return
    now = datetime.now(UTC).isoformat(timespec="seconds")
    for doc_id, (title, reason) in _OFF_DISEASE.items():
        removed = bind.execute(
            sa.text("DELETE FROM guideline_source_documents WHERE disease_slug = :slug AND doc_id = :doc"),
            {"slug": _SLUG, "doc": doc_id},
        ).rowcount
        if removed and _has("guideline_shelf_considered"):
            bind.execute(
                sa.text("DELETE FROM guideline_shelf_considered WHERE disease_slug = :slug AND doc_id = :doc"),
                {"slug": _SLUG, "doc": doc_id},
            )
            bind.execute(
                sa.text(
                    "INSERT INTO guideline_shelf_considered (disease_slug, doc_id, title, reason, category, considered_at) "
                    "VALUES (:slug, :doc, :title, :reason, 'off-topic', :at)"
                ),
                {"slug": _SLUG, "doc": doc_id, "title": title, "reason": reason, "at": now},
            )


def downgrade() -> None:
    """No-op: another disease's chapter must never be put back on this shelf."""
