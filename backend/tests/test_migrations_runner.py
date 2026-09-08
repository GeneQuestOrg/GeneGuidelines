"""The schema comes up with the code, or the process dies trying.

Migrations were applied by hand and it cost production twice in one day: once when
code shipped reading a column whose migration nobody had run, and once when a feature
had to be built around the schema instead of with it because running one felt too
risky to bundle into a deploy.

That is structural. Deploying code and migrating the database are one release, and
splitting them across a pipeline and a human guarantees they drift.
"""

from __future__ import annotations

import pytest

from backend import migrations_runner


def test_no_database_url_is_a_skip_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests, tooling and one-off scripts import the app without a database."""
    monkeypatch.setattr("backend.config.DB_URL", "")

    assert migrations_runner.upgrade_to_head() is None


def test_a_failing_migration_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point. An app that boots against a half-applied schema serves
    confident wrong answers; a dead process is a visible broken deploy."""
    import alembic.command

    monkeypatch.setattr("backend.config.DB_URL", "postgresql://x/y")
    monkeypatch.setattr(migrations_runner, "_ROOT", migrations_runner._ROOT)

    def _boom(*args, **kwargs):
        raise RuntimeError("migration exploded")

    monkeypatch.setattr(alembic.command, "upgrade", _boom)

    with pytest.raises(Exception):
        migrations_runner.upgrade_to_head("postgresql://user:pass@127.0.0.1:1/nope")


def test_the_lock_key_is_stable() -> None:
    """Two processes only serialise if they agree on the number; changing it silently
    disables the guard rather than failing."""
    assert migrations_runner._LOCK_KEY == 0x6D6967726174696F & 0x7FFFFFFFFFFFFFFF


def test_running_migrations_does_not_silence_the_application_log() -> None:
    """The bug this file's own failures uncovered.

    logging.config.fileConfig defaults to disable_existing_loggers=True. That was
    harmless while alembic only ever ran from a CLI; now that migrations run inside
    the application process at start-up it would silence every logger the app had
    already configured — including the run log the engine writes its trace to. The
    symptom in the suite was two unrelated logging tests failing; the symptom in
    production would have been a silent engine.
    """
    import pathlib

    env = (pathlib.Path(__file__).resolve().parents[2] / "alembic" / "env.py").read_text()

    assert "disable_existing_loggers=False" in env, (
        "alembic's fileConfig will silence the application's own loggers"
    )


def test_the_runner_never_reaches_for_psycopg2() -> None:
    """This project talks to Postgres through psycopg 3.

    A bare "postgresql://" URL makes SQLAlchemy import psycopg2, which is not a
    dependency — it happened to be installed on the developer machine and was absent
    in CI and in the container. The same shape as reaching for bs4: green locally,
    dead where it matters.
    """
    for url in ("postgresql://u:p@h/db", "postgres://u:p@h/db"):
        assert migrations_runner._psycopg3(url).startswith("postgresql+psycopg://")

    # Already-qualified and non-Postgres URLs pass through untouched.
    assert migrations_runner._psycopg3("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"
    assert migrations_runner._psycopg3("sqlite:///x.db") == "sqlite:///x.db"


def test_the_normal_path_uses_the_application_engine_factory() -> None:
    """One place decides how this project connects. A second engine built by hand is
    how the driver drifted apart in the first place."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parents[1] / "migrations_runner.py").read_text()

    assert "from backend.shared.persistence.engine import get_engine" in source


def test_the_schema_has_two_owners_and_that_is_why_startup_migration_is_off() -> None:
    """Records a dead end so nobody walks it twice.

    Running alembic from the app's start-up is the obvious fix for hand-applied
    migrations, and it cannot work here yet: the schema has two owners. Alembic's
    baseline creates `catalog_stats` and so does imperative CREATE TABLE IF NOT EXISTS
    in content_db, so replaying the baseline dies on a duplicate. Stamping the baseline
    to skip it then dies on `private_contexts`, which the imperative path never
    creates. They produce different, partially overlapping schemas — neither replaying
    nor stamping tells the truth about what is there.

    Unifying ownership is the real fix and is its own piece of work.
    """
    import pathlib as _pl

    content_db = (_pl.Path(__file__).resolve().parents[1] / "content_db.py").read_text()

    assert "CREATE TABLE IF NOT EXISTS catalog_stats" in content_db, (
        "the imperative creation path is gone — schema ownership may now be unified, "
        "so re-evaluate running migrations at start-up"
    )
