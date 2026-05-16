"""SQLAlchemy ``Engine`` factory, pointed at the same SQLite file used by the
legacy ``backend.database`` module.

This factory is process-scoped: one ``Engine`` per process, lazily created on
first call. New repositories get a connection from it via
:class:`backend.shared.persistence.base_repo.BaseSqlalchemyRepo`.
"""

from __future__ import annotations

from threading import Lock
from typing import Optional

from sqlalchemy import Engine, create_engine, event
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
    from ...config import DB_PATH

    url = f"sqlite:///{DB_PATH}"
    engine = create_engine(
        url,
        future=True,
        # SQLite needs check_same_thread=False so FastAPI workers can share
        # the engine across thread-pool tasks.
        connect_args={"check_same_thread": False},
        # Same defaults the legacy raw-sqlite3 code uses elsewhere.
        echo=False,
    )
    _enable_sqlite_pragmas(engine)
    return engine


def _enable_sqlite_pragmas(engine: Engine) -> None:
    """Mirror the PRAGMAs the legacy ``backend.database.get_connection`` sets."""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cur = dbapi_connection.cursor()
        try:
            cur.execute("PRAGMA foreign_keys = ON")
            cur.execute("PRAGMA journal_mode = WAL")
        finally:
            cur.close()


def reset_engine_for_tests() -> None:
    """Drop the cached engine. Tests use this to switch between databases."""
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None


__all__ = ["get_engine", "reset_engine_for_tests", "Connection"]
