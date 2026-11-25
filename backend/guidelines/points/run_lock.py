"""One run per disease at a time, across processes.

The after-synthesis hook runs in the research worker and the backfill in the API process, so an in-process set alone cannot stop both from paying for the same disease. ``PostgresRunLock`` takes a session-level advisory lock (``pg_try_advisory_lock``) on a dedicated AUTOCOMMIT connection held for the whole run, and releases it in ``finally``; a second run finds the lock taken and skips instead of waiting. The in-process set stays as the fast path and is all a non-Postgres database (tests, labs) gets.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ...shared.persistence.engine import get_engine

log = logging.getLogger(__name__)


class RunLock(Protocol):
    """``with lock.hold(slug) as held:`` — ``held`` is False when another run for the disease is in progress."""

    def hold(self, slug: str) -> AbstractContextManager[bool]: ...


def _key(slug: str) -> int:
    """A stable signed 64-bit advisory-lock key for one disease."""
    digest = hashlib.sha256(f"guideline_points:{slug}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


class InProcessRunLock:
    """One run per disease within this process."""

    def __init__(self) -> None:
        self._running: set[str] = set()

    @contextmanager
    def hold(self, slug: str) -> Iterator[bool]:
        if slug in self._running:
            yield False
            return
        self._running.add(slug)
        try:
            yield True
        finally:
            self._running.discard(slug)


class PostgresRunLock:
    """One run per disease across every process that shares the database."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine
        self._local = InProcessRunLock()

    def _get_engine(self) -> Engine:
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    @contextmanager
    def hold(self, slug: str) -> Iterator[bool]:
        with self._local.hold(slug) as held:
            if not held:
                yield False
                return
            engine = self._get_engine()
            if engine.dialect.name != "postgresql":
                yield True
                return
            key = _key(slug)
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                if not conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar():
                    yield False
                    return
                try:
                    yield True
                finally:
                    try:
                        conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                    except Exception:  # closing the connection releases a session lock anyway
                        log.warning("guideline points: advisory unlock failed for %s", slug, exc_info=True)


__all__ = ["InProcessRunLock", "PostgresRunLock", "RunLock"]
