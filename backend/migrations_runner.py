"""Bring the database schema up to head — on demand, not at start-up.

Written to close a real gap: migrations here are applied by hand, and that cost
production twice in one day. Once when code shipped reading a column whose migration
nobody had run, and once when a feature had to be built around the schema instead of
with it, because bundling a migration into a deploy felt riskier than it should have.

Running it from the application's start-up was the obvious fix and it does not work,
for a reason worth writing down rather than rediscovering. The schema here has TWO
owners: alembic migrations, and imperative `CREATE TABLE IF NOT EXISTS` in
`content_db`/`database`. They never met while migrations were run by hand against an
already-stamped database. From start-up they do, and they disagree — the baseline
migration dies on `catalog_stats`, which the imperative path already created, while
stamping the baseline to skip it then dies on `private_contexts`, which the imperative
path never creates. The two owners produce different, partially overlapping schemas,
so neither replaying nor stamping is truthful.

Unifying that ownership is the actual fix and it is its own piece of work. Until then
this runs deliberately:

    python3 -m backend.migrations_runner

Failures are not swallowed. A half-applied schema that still serves traffic is the
exact failure this exists to prevent.
"""

from __future__ import annotations

import logging
import pathlib

log = logging.getLogger(__name__)

_ROOT = pathlib.Path(__file__).resolve().parent.parent
# Chosen once, arbitrary, must stay stable: two processes agree to serialise on it.
_LOCK_KEY = 0x6D6967726174696F & 0x7FFFFFFFFFFFFFFF
# The revision whose tables the imperative creation path also produces.
_BASELINE_REVISION = "dd31c5539990"
# Present iff something already built the schema — either alembic or the imperative path.
_PROBE_TABLE = "catalog_stats"


def _has_application_tables(connection) -> bool:
    from sqlalchemy import text

    return bool(
        connection.execute(
            text("SELECT to_regclass(:name)"), {"name": _PROBE_TABLE}
        ).scalar()
    )


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
                if before is None and _has_application_tables(connection):
                    # Schema here has two owners: alembic, and imperative
                    # `CREATE TABLE IF NOT EXISTS` in content_db/database. They never
                    # met while migrations were run by hand on an already-stamped
                    # database. Running from start-up they do, and the baseline
                    # migration dies on a table the imperative path already made.
                    #
                    # Adopting the existing schema is what `stamp` is for: mark it as
                    # the baseline rather than replaying a creation that has happened,
                    # then let every later migration apply normally.
                    log.warning("migrations: existing schema with no version — stamping baseline")
                    command.stamp(config, _BASELINE_REVISION)
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    print(f"schema at: {upgrade_to_head()}")
