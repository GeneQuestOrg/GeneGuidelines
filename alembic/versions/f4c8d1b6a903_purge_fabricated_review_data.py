"""purge fabricated review signals, aggregates and change requests

Revision ID: f4c8d1b6a903
Revises: 19c5c5f78294
Create Date: 2026-08-24 12:00:00.000000

The code no longer seeds any of this, but deleting a seed does not delete rows a
previous deploy already wrote — production kept serving all of it. This migration
removes the fabricated review record itself.

1. ``guideline_synthesis_signals`` — emptied. There is no write path for
   section-level signals, so every row in this table came from the seed:
   production served "7 clinicians found this useful · 3 verified" for fibrous
   dysplasia and a flag note signed "Verified reviewer" while no clinician had
   ever voted on anything.

2. ``guideline_suggestions.signal`` — recomputed from ``guideline_suggestion_votes``,
   which is the record of real ratings (SIG-1). Suggestions with no votes go to
   zeros; genuine votes are preserved exactly. Mirrors ``_aggregate()`` in
   backend/guidelines/repository.py.

3. ``content_prs`` — the five AI-authored change requests seeded as a live review
   queue, each attributed to a reviewer called "specialist network", one of them a
   paediatric denosumab dosing schedule. Deleted by id, so a real PR created later
   is never touched.

Nobody signs anything off on this platform (ADR 008): a clinician's rating is a
signal for the next reader, not an approval. No seeded row may imply otherwise.

Not reversible: downgrade cannot resurrect fabricated numbers, and would not want
to. It is a no-op on purpose.

Deploy note: ``export DB_URL`` before ``alembic upgrade head``.
"""
import json
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4c8d1b6a903"
down_revision: Union[str, None] = "19c5c5f78294"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The seeded review queue (backend/content_seed.json before this change).
_SEEDED_PR_IDS = ("PR-138", "PR-139", "PR-140", "PR-141", "PR-142")

_VERDICTS = ("useful", "not", "wrong")


def _has(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def _recompute_suggestion_signals(bind: sa.engine.Connection) -> None:
    """Fold real votes into each suggestion's aggregate.

    Done in Python rather than one UPDATE…FROM: the set is tiny (tens of rows),
    and the SQL version needs ``json_build_object``, which does not exist on
    SQLite — where offline alembic runs.
    """
    votes: dict[tuple[str, str], dict[str, int]] = {}
    for slug, suggestion_id, verdict, verified in bind.execute(
        sa.text(
            "SELECT disease_slug, suggestion_id, verdict, verified_vote "
            "FROM guideline_suggestion_votes"
        )
    ):
        if verdict not in _VERDICTS:
            continue
        tally = votes.setdefault(
            (slug, suggestion_id),
            {"useful": 0, "not": 0, "wrong": 0, "ratings": 0, "verified": 0},
        )
        tally[verdict] += 1
        tally["ratings"] += 1
        if verified:
            tally["verified"] += 1

    empty = {"useful": 0, "not": 0, "wrong": 0, "ratings": 0, "verified": 0}
    rows = bind.execute(sa.text("SELECT disease_slug, id FROM guideline_suggestions")).all()
    for slug, suggestion_id in rows:
        bind.execute(
            sa.text(
                "UPDATE guideline_suggestions SET signal = :signal "
                "WHERE disease_slug = :slug AND id = :id"
            ),
            {
                "signal": json.dumps(votes.get((slug, suggestion_id), empty)),
                "slug": slug,
                "id": suggestion_id,
            },
        )


def upgrade() -> None:
    bind = op.get_bind()

    if _has("guideline_synthesis_signals"):
        bind.execute(sa.text("DELETE FROM guideline_synthesis_signals"))

    if _has("guideline_suggestions") and _has("guideline_suggestion_votes"):
        _recompute_suggestion_signals(bind)

    if _has("content_prs"):
        bind.execute(
            sa.text("DELETE FROM content_prs WHERE id IN :ids").bindparams(
                sa.bindparam("ids", value=_SEEDED_PR_IDS, expanding=True)
            )
        )


def downgrade() -> None:
    """No-op: fabricated review data is not restored."""
