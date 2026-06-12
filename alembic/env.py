"""Alembic environment.

Wires the :data:`backend.shared.persistence.schema.metadata` registry into
Alembic so ``alembic revision --autogenerate`` can diff against the source-of-
truth ``Table`` definitions.

Scope (Phase 1): the metadata only knows the *content* domain tables today
(``diseases``, ``guideline_documents``, ``content_prs``, ``catalog_stats``,
``care_pathways``). Other tables (``tickets``, ``flow_definitions``, …) are
still created and owned by ``backend.database`` and are intentionally hidden
from Alembic via :func:`include_object` so autogenerate does not propose
dropping them. They join the metadata as their owning modules get refactored
in Phase 2.
"""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from sqlalchemy import pool
from sqlalchemy.engine import Connection

from alembic import context

from backend.shared.persistence.engine import get_engine
from backend.shared.persistence.schema import metadata as content_metadata

# Import the ORM-mapped domains so their tables register on the shared
# ``metadata`` before autogenerate diffs against it. ``doctor_contributions``
# (DOC-5) is the first ORM domain; importing it attaches ``doctor_submissions``
# / ``parent_recs`` to ``content_metadata``.
import backend.doctor_contributions.orm  # noqa: E402,F401


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = content_metadata


_KNOWN_TABLES = set(content_metadata.tables.keys())


def include_object(
    obj: Any,
    name: str,
    type_: str,
    reflected: bool,
    compare_to: Any,
) -> bool:
    """Hide tables not yet declared in :data:`content_metadata` from autogenerate.

    Without this filter, ``alembic revision --autogenerate`` would propose
    DROP statements for every table that exists in the database but is not
    yet declared in ``schema.py``. Phase 2 will gradually move those tables
    into the metadata; until then they are managed by the legacy
    ``backend.database._ensure_*`` chain.
    """
    if type_ == "table" and reflected:
        return name in _KNOWN_TABLES
    return True


def run_migrations_offline() -> None:
    """Generate SQL scripts without a live database connection."""
    url = str(get_engine().url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE.
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the live engine (same one the backend uses)."""
    connectable = get_engine()

    with connectable.connect() as connection:
        _configure_online(connection)

        with context.begin_transaction():
            context.run_migrations()


def _configure_online(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        render_as_batch=True,
    )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
