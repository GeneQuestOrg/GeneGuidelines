"""SQLAlchemy ``Engine`` factory — Postgres via ``DB_URL``."""

from __future__ import annotations

from threading import Lock
from typing import Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import Connection


_engine: Optional[Engine] = None
_engine_lock = Lock()


def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy ``Engine`` (lazy, thread-safe init)."""
    global _engine
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None:
            _engine = _build_engine()
    return _engine


def _build_engine() -> Engine:
    try:
        from ...config import DB_URL
    except ImportError:
        from config import DB_URL  # type: ignore[no-redef]

    if not DB_URL:
        raise RuntimeError(
            "DB_URL is required for SQLAlchemy engine (postgresql://user:pass@host:5432/dbname)."
        )
    url = DB_URL
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    # pool_pre_ping: validate each pooled connection (lightweight SELECT 1) before use,
    # transparently discarding+reconnecting dead ones. Azure Postgres (burstable) drops
    # idle connections / restarts for maintenance, which otherwise surfaces as an
    # intermittent 500 "psycopg.errors.AdminShutdown: terminating connection due to
    # administrator command" on the first request after the drop.
    # pool_recycle: proactively retire connections older than 5 min so we never hand out
    # one the server has already silently closed.
    return create_engine(
        url,
        future=True,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
    )


def reset_engine_for_tests() -> None:
    """Drop the cached engine. Tests use this when switching databases."""
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None


__all__ = ["get_engine", "reset_engine_for_tests", "Connection"]
