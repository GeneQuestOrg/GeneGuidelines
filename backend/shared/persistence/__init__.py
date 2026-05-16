"""Persistence layer — SQLAlchemy 2.0 Core (NOT ORM).

Architecture rationale: see ``docs/wizja-architektury-technicznej.md`` §3.4.

Public API:

- :data:`backend.shared.persistence.schema.metadata` — single ``MetaData`` instance
  carrying every ``Table`` definition. Alembic targets this object.
- :func:`backend.shared.persistence.engine.get_engine` — process-wide SQLAlchemy
  ``Engine`` pointed at the same SQLite file ``backend.database`` uses.
- :class:`backend.shared.persistence.base_repo.BaseSqlalchemyRepo` — connection /
  transaction context manager that concrete repositories subclass.

New modules write their repository using SQLAlchemy Core ``select`` / ``insert``
/ ``update`` against the shared ``Table`` objects. Existing code that still
uses raw SQL through ``backend.database`` is grandfathered until Phase 2.
"""

from .engine import get_engine
from .schema import metadata

__all__ = ["get_engine", "metadata"]
