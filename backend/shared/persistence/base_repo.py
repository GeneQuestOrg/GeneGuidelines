"""Base class for SQLAlchemy 2.0 Core repositories.

Repositories live inside their owning domain module
(``backend/<module>/repository.py``) and extend :class:`BaseSqlalchemyRepo`
solely to inherit the ``_conn()`` transactional context manager. Everything
else — query composition, row → domain mapping — stays in the concrete
repository so each domain reads as a self-contained file.

Why not just import ``get_engine`` everywhere:

- The context manager wraps every read/write in an explicit ``BEGIN`` /
  ``COMMIT`` / ``ROLLBACK`` so domain code never forgets to commit.
- Tests can subclass with an in-memory engine without touching the rest of
  the codebase.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine
from sqlalchemy.engine import Connection

from .engine import get_engine


class BaseSqlalchemyRepo:
    """Shared transactional plumbing for Core-based repositories."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()

    @contextmanager
    def _conn(self) -> Iterator[Connection]:
        """Yield a connection inside a transaction.

        Commits on normal exit, rolls back on exception. Use for any
        statement that touches the database, even pure reads, so the
        connection is released back to the pool deterministically.
        """
        with self._engine.connect() as conn:
            with conn.begin():
                yield conn


__all__ = ["BaseSqlalchemyRepo"]
