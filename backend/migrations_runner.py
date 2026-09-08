"""Bring the database schema up to head on start-up.

Migrations here were applied by hand, and that cost production twice in one day:
once when code shipped reading a column whose migration nobody had run yet, and once
when a feature had to be built around the schema rather than with it because running
one felt too risky to bundle into a deploy.

The gap is structural, not a discipline problem. Deploying code and migrating the
database are one act — a release — and splitting them across a pipeline and a human
guarantees they drift.

Safe to do at start-up here specifically because the app runs at maxReplicas: 1, so
there is no second instance to race. A Postgres advisory lock is taken anyway, since
"we only ever run one replica" is the kind of assumption that changes quietly in a
portal six months from now.

Fails loudly. A migration that half-applies and then lets the app serve traffic is
the exact failure this exists to prevent: the process should die and the deploy should
be visibly broken, not quietly wrong about what the database contains.
"""

from __future__ import annotations

import logging
import pathlib

log = logging.getLogger(__name__)

_ROOT = pathlib.Path(__file__).resolve().parent.parent
# Chosen once, arbitrary, must stay stable: two processes agree to serialise on it.
_LOCK_KEY = 0x6D6967726174696F & 0x7FFFFFFFFFFFFFFF


def _psycopg3(url: str) -> str:
    """Pin the driver the rest of the app uses, whatever shape the URL arrives in."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def upgrade_to_head(db_url: str | None = None) -> str | None:
    """Run alembic to head. Returns the revision now applied, or None when skipped."""
    from backend.config import DB_URL as _CONFIGURED

    url = (db_url or _CONFIGURED or "").strip()
    if not url:
        log.info("migrations: no DB_URL, skipping")
        return None

    ini = _ROOT / "alembic.ini"
    if not ini.exists():
        log.warning("migrations: alembic.ini not found at %s, skipping", ini)
        return None

    from alembic import command
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine, text

    # This project talks to Postgres through psycopg 3. A bare "postgresql://" URL
    # makes SQLAlchemy reach for psycopg2, which is not a dependency here — it
    # happened to be installed on the developer machine and was absent in CI and in
    # the container. Same shape of failure as reaching for bs4: works locally, dies
    # where it matters.
    url = _psycopg3(url)

    config = Config(str(ini))
    config.set_main_option("script_location", str(_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url)

    # Reuse the application's own engine factory rather than building a second one:
    # it already normalises the URL to psycopg 3, and one place deciding how this
    # project connects is the whole point. An explicit URL (tests) still gets its own.
    if db_url:
        engine = create_engine(_psycopg3(db_url))
    else:
        from backend.shared.persistence.engine import get_engine

        engine = get_engine()
    try:
        with engine.connect() as connection:
            # Serialise across processes. Released when the connection closes, so a
            # crashed migrator cannot wedge every future boot.
            connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": _LOCK_KEY})
            try:
                before = MigrationContext.configure(connection).get_current_revision()
                command.upgrade(config, "head")
                after = MigrationContext.configure(connection).get_current_revision()
            finally:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})
    finally:
        engine.dispose()

    if before == after:
        log.info("migrations: already at %s", after)
    else:
        log.warning("migrations: upgraded %s -> %s", before, after)
    return after
