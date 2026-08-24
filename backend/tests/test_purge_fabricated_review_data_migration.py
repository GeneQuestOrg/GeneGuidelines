"""Alembic ``f4c8d1b6a903`` actually removes the fabricated review record.

The seed files no longer contain any of it, but production had already written
those rows, and a seed deletion does not delete rows. This migration is the part
that reaches live data, and it cannot be verified by reading the seed — so it is
exercised here end to end on a throwaway SQLite file: fabricated rows plus one
genuine vote go in, the revision runs, and the genuine vote must survive while
everything invented disappears.

Follows the pattern of test_content_translation_scaffolding: stamp at the prior
head so ``upgrade`` runs only the revision under test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

REPO_ROOT = Path(__file__).resolve().parents[2]

_PRIOR_HEAD = "19c5c5f78294"
_REVISION = "f4c8d1b6a903"

# Minimal shapes of the three tables the revision touches (see guidelines/orm.py
# and content_db.py). Hand-written so the test does not depend on the full
# historical migration chain, which cannot run on a fresh database.
_DDL = (
    """
    CREATE TABLE guideline_synthesis_signals (
        disease_slug TEXT NOT NULL,
        section_id TEXT NOT NULL,
        up INTEGER NOT NULL DEFAULT 0,
        flags INTEGER NOT NULL DEFAULT 0,
        verified INTEGER NOT NULL DEFAULT 0,
        flag_notes TEXT,
        PRIMARY KEY (disease_slug, section_id)
    )
    """,
    """
    CREATE TABLE guideline_suggestions (
        disease_slug TEXT NOT NULL,
        id TEXT NOT NULL,
        signal TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY (disease_slug, id)
    )
    """,
    """
    CREATE TABLE guideline_suggestion_votes (
        disease_slug TEXT NOT NULL,
        suggestion_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        verdict TEXT NOT NULL,
        verified_vote INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (disease_slug, suggestion_id, user_id)
    )
    """,
    """
    CREATE TABLE content_prs (
        id TEXT PRIMARY KEY,
        disease_slug TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL
    )
    """,
)

_FABRICATED_SIGNAL = json.dumps(
    {"useful": 7, "not": 0, "wrong": 0, "ratings": 7, "verified": 3}
)


@pytest.fixture
def engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from backend import config as app_config
    from backend.shared.persistence import engine as engine_mod

    db_file = tmp_path / "purge.db"
    monkeypatch.setattr(app_config, "DB_URL", f"sqlite:///{db_file}")
    engine_mod.reset_engine_for_tests()
    try:
        yield engine_mod.get_engine()
    finally:
        engine_mod.reset_engine_for_tests()


def _seed(engine) -> None:
    with engine.begin() as conn:
        for ddl in _DDL:
            conn.execute(text(ddl))

        # A section signal nobody could have produced: there is no write path.
        conn.execute(
            text(
                "INSERT INTO guideline_synthesis_signals "
                "(disease_slug, section_id, up, flags, verified, flag_notes) VALUES "
                "('fd', 'histopathology', 5, 1, 2, "
                "'[{\"who\": \"Verified reviewer\", \"text\": \"...\"}]')"
            )
        )

        # Two suggestions with invented aggregates; only the first has a real vote.
        for suggestion_id in ("sg-real", "sg-invented"):
            conn.execute(
                text(
                    "INSERT INTO guideline_suggestions (disease_slug, id, signal) "
                    "VALUES ('mas', :id, :signal)"
                ),
                {"id": suggestion_id, "signal": _FABRICATED_SIGNAL},
            )
        conn.execute(
            text(
                "INSERT INTO guideline_suggestion_votes "
                "(disease_slug, suggestion_id, user_id, verdict, verified_vote) "
                "VALUES ('mas', 'sg-real', 'auth0|clinician', 'useful', 1)"
            )
        )

        conn.execute(
            text(
                "INSERT INTO content_prs (id, disease_slug, title, status) VALUES "
                "('PR-142', 'fd', 'Seeded change request', 'under-review'), "
                "('PR-500', 'fd', 'A real one, created later', 'pending')"
            )
        )


def _upgrade() -> None:
    from alembic.config import Config

    from alembic import command

    # No .ini path on purpose: env.py calls fileConfig() when one is set, which
    # disables existing loggers process-wide and breaks later tests in the run.
    cfg = Config()
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    command.stamp(cfg, _PRIOR_HEAD)
    command.upgrade(cfg, _REVISION)


def test_migration_purges_fabricated_data_and_keeps_the_real_vote(engine) -> None:
    _seed(engine)

    _upgrade()

    with engine.connect() as conn:
        # 1. Section signals: every row was seeded, so the table empties.
        assert conn.execute(text("SELECT COUNT(*) FROM guideline_synthesis_signals")).scalar() == 0

        # 2. Aggregates come from real votes only.
        signals = {
            row[0]: json.loads(row[1])
            for row in conn.execute(text("SELECT id, signal FROM guideline_suggestions"))
        }
        assert signals["sg-real"] == {
            "useful": 1,
            "not": 0,
            "wrong": 0,
            "ratings": 1,
            "verified": 1,
        }
        assert signals["sg-invented"] == {
            "useful": 0,
            "not": 0,
            "wrong": 0,
            "ratings": 0,
            "verified": 0,
        }

        # 3. Only the seeded change requests go; a later real PR is untouched.
        remaining = [r[0] for r in conn.execute(text("SELECT id FROM content_prs"))]
        assert remaining == ["PR-500"]


def test_migration_is_a_noop_when_the_tables_do_not_exist(engine) -> None:
    """A fresh database must not fail the upgrade."""
    _upgrade()  # no tables created — the guards must skip every step
