#!/usr/bin/env python3
"""One-time migration: SQLite ``tickets.db`` → Azure Postgres.

Usage:
    DB_URL="postgresql://ggapp:...@host:5432/geneguidelines?sslmode=require" \\
        python3 scripts/migrate_sqlite_to_postgres.py /tmp/prod-tickets.db

Strategy:
- Insert every row from SQLite into Postgres using ``ON CONFLICT DO NOTHING``
  without an explicit target. Any row that collides on a PK or UNIQUE
  constraint is skipped — the existing Postgres seed row wins.
- Tables are migrated in dependency order so foreign keys resolve.
- Tables whose primary key is ``id SERIAL`` get their sequence bumped to
  ``MAX(id) + 1`` after migration so future inserts do not collide.
- ``sqlite_*`` internal tables and the ``catalog_stats`` singleton are left
  alone — Postgres already has them.

Idempotent: re-running is a no-op (everything conflicts).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import Any

import psycopg


# Migration order: parents first, children after. Tables NOT listed are skipped.
TABLE_ORDER: list[str] = [
    # leaf seed
    "_seed_done",
    "tool_catalog",
    "tool_implementations",
    # flows (independent)
    "flow_definitions",
    "flow_edges",
    # tickets graph
    "tickets",
    "comments",
    "tool_requests",
    # content
    "diseases",
    "guideline_documents",
    "official_guideline_pointers",
    "content_prs",
    "trials",
    "disease_trials",
    "foundations",
    "disease_foundations",
    "therapies",
    "care_pathways",
    "private_contexts",
    # runs
    "guideline_run_results",
    "doctor_finder_run_results",
]

# Tables whose ``id`` is SERIAL — sequence must be bumped after migration.
SERIAL_TABLES: set[str] = {
    "tickets",
    "comments",
    "tool_catalog",
    "tool_requests",
    "tool_implementations",
    "flow_definitions",
    "flow_edges",
    "therapies",
    "foundations",
    "private_contexts",
}


def _read_table(src: sqlite3.Connection, table: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    cur = src.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    rows = [tuple(r) for r in cur.fetchall()]
    return cols, rows


def _bulk_insert(
    dst: psycopg.Connection,
    table: str,
    cols: list[str],
    rows: list[tuple[Any, ...]],
) -> tuple[int, int]:
    """Insert rows with ON CONFLICT DO NOTHING. Returns (attempted, inserted)."""
    if not rows:
        return 0, 0
    cols_csv = ", ".join(cols)
    placeholders = ", ".join(["%s"] * len(cols))
    sql = (
        f"INSERT INTO {table} ({cols_csv}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT DO NOTHING"
    )
    inserted = 0
    with dst.cursor() as cur:
        for row in rows:
            cur.execute(sql, row)
            inserted += cur.rowcount or 0
    return len(rows), inserted


def _bump_sequence(dst: psycopg.Connection, table: str) -> None:
    with dst.cursor() as cur:
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table}), 1), "
            f"COALESCE((SELECT MAX(id) FROM {table}) IS NOT NULL, false))"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sqlite_path", help="Path to SQLite source DB (e.g. /tmp/prod-tickets.db)")
    parser.add_argument(
        "--db-url",
        default=os.environ.get("DB_URL", ""),
        help="Postgres URL (default: $DB_URL)",
    )
    args = parser.parse_args()

    if not args.db_url:
        print("DB_URL not set (use --db-url or env)", file=sys.stderr)
        return 1
    if not os.path.exists(args.sqlite_path):
        print(f"SQLite not found: {args.sqlite_path}", file=sys.stderr)
        return 1

    src = sqlite3.connect(args.sqlite_path)
    src.row_factory = sqlite3.Row

    print(f"Source: {args.sqlite_path}")
    print(f"Target: {args.db_url.split('@')[-1].split('?')[0]}")
    print()

    summary: list[tuple[str, int, int]] = []
    with psycopg.connect(args.db_url) as dst:
        for table in TABLE_ORDER:
            try:
                cols, rows = _read_table(src, table)
            except sqlite3.OperationalError as exc:
                print(f"  {table:<30} SKIP (source missing): {exc}")
                continue
            attempted, inserted = _bulk_insert(dst, table, cols, rows)
            print(f"  {table:<30} attempted={attempted:>4}  inserted={inserted:>4}  skipped={attempted - inserted:>4}")
            summary.append((table, attempted, inserted))
        dst.commit()

        print()
        print("Bumping SERIAL sequences:")
        for table in SERIAL_TABLES:
            try:
                _bump_sequence(dst, table)
                print(f"  {table:<30} OK")
            except Exception as exc:  # noqa: BLE001 — best-effort across mixed schemas
                print(f"  {table:<30} skipped ({exc})")
        dst.commit()

    src.close()

    print()
    print(f"Done. Migrated {sum(i for _, _, i in summary)} rows across {len(summary)} tables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
