"""Case-insensitive ORDER BY helpers (Postgres ``lower``)."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.sql.elements import ColumnElement


def nocase_order(column: ColumnElement) -> ColumnElement:
    return func.lower(column)


def nocase_order_sql(column: str = "name") -> str:
    return f"ORDER BY lower({column})"


__all__ = ["nocase_order", "nocase_order_sql"]
