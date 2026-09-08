"""Structured answers on parent contributions: what_helped, how_found.

The submission form asked one question, "why do you recommend them", and got
sentiment back. It now asks the two things a family knows and no registry records:
what the clinician got right, and how they were reached. Those shipped first inside
the existing free-text column behind stable markers, because migrations here were
applied by hand and bundling one into a deploy felt riskier than it should have.

This gives them real columns and lifts every historical answer out of the markers, so
nothing written in the interim is stranded in prose.

Revision ID: d3a71f5c2e88
Revises: c9f3a5d81b47
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d3a71f5c2e88"
down_revision = "c9f3a5d81b47"
branch_labels = None
depends_on = None

_TABLES = {"doctor_submissions": "note", "parent_recs": "text"}

_WHAT = "[what-helped]"
_HOW = "[how-found]"


def _split(text: str) -> tuple[str, str]:
    """(what_helped, how_found) out of a marker-composed note.

    Done in Python rather than SQL because Postgres POSIX regex has no lookahead, and
    the SQL version of this failed only when a row actually existed — it passed
    against empty tables and would have broken the first deploy that had data.

    Deliberately duplicated from backend/doctor_contributions/answers.py: a migration
    has to keep working when that module is refactored years from now.
    """
    positions = sorted(
        (text.find(marker), marker) for marker in (_WHAT, _HOW) if marker in text
    )
    out = {_WHAT: "", _HOW: ""}
    for index, (start, marker) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(text)
        out[marker] = text[start + len(marker) : end].strip()
    return out[_WHAT], out[_HOW]


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("what_helped", sa.Text(), nullable=False, server_default=""))
        op.add_column(table, sa.Column("how_found", sa.Text(), nullable=False, server_default=""))

    connection = op.get_bind()
    for table, column in _TABLES.items():
        rows = connection.execute(
            sa.text(f"SELECT id, {column} AS body FROM {table} WHERE {column} LIKE :w OR {column} LIKE :h"),
            {"w": f"%{_WHAT}%", "h": f"%{_HOW}%"},
        ).fetchall()
        for row in rows:
            what_helped, how_found = _split(row.body or "")
            connection.execute(
                sa.text(f"UPDATE {table} SET what_helped = :w, how_found = :h WHERE id = :id"),
                {"w": what_helped, "h": how_found, "id": row.id},
            )


def downgrade() -> None:
    # The prose column still carries the markers, so dropping these loses nothing.
    for table in _TABLES:
        op.drop_column(table, "how_found")
        op.drop_column(table, "what_helped")
