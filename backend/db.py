"""Postgres connection for the legacy raw-SQL layer (``database.py``, ``content_db.py``).

Production requires ``DB_URL``. Kaggle snapshot apps stay on the frozen SQLite
image — this module is not used there.
"""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

try:
    from .config import DB_URL
except ImportError:
    from config import DB_URL  # type: ignore[no-redef]


def get_connection() -> psycopg.Connection:
    if not DB_URL:
        raise RuntimeError(
            "DB_URL is required (postgresql://user:pass@host:5432/dbname). "
            "Local dev: docker run postgres:16 and export DB_URL."
        )
    return psycopg.connect(DB_URL, row_factory=dict_row)


def table_exists(conn: psycopg.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(conn: psycopg.Connection, table_name: str) -> set[str]:
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table_name,),
    ).fetchall()
    return {str(row["column_name"]) for row in rows}


__all__ = ["get_connection", "table_columns", "table_exists"]
