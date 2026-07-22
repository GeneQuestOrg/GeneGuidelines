"""PR1 content-translation scaffolding — config, locale resolver, migration.

Covers the three pieces PR1 adds without any behaviour change:

1. Config defaults: ``TRANSLATION_TARGET_LOCALES`` defaults to ``["pl"]`` and
   ``TRANSLATION_MODEL`` resolves exactly like ``WIDER_SEARCH_JUDGE_MODEL``
   (frontier model / None, independent of SINGLE_LLM_MODE).
2. ``resolve_locale`` / ``normalize_locale`` allow-list: a served locale is
   returned as-is (case/space-insensitive), anything unknown or None → ``"en"``.
3. The Alembic migration ``e2f9a1c7b4d3`` up→down→up against a throwaway SQLite,
   plus a ``metadata.create_all`` parity check that the two new tables are
   declared on the shared metadata.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

REPO_ROOT = Path(__file__).resolve().parents[2]


# -- 1. config defaults ------------------------------------------------------


@pytest.mark.skipif(
    "TRANSLATION_TARGET_LOCALES" in os.environ,
    reason="env override present — default cannot be asserted",
)
def test_translation_target_locales_default_is_pl() -> None:
    from backend import config

    assert config.TRANSLATION_TARGET_LOCALES == ["pl"]


@pytest.mark.skipif(
    bool((os.environ.get("TRANSLATION_MODEL") or "").strip())
    or bool((os.environ.get("WIDER_SEARCH_JUDGE_MODEL") or "").strip()),
    reason="explicit model env override present — mirror invariant not assertable",
)
def test_translation_model_mirrors_wider_search_judge_resolution() -> None:
    """TRANSLATION_MODEL resolves by the same rule as WIDER_SEARCH_JUDGE_MODEL.

    Both default to a frontier ``openai:`` spec when an OpenAI key is present and
    to ``None`` otherwise, resolved independently of SINGLE_LLM_MODE. With neither
    env override set they must therefore be equal.
    """
    from backend import config

    assert config.TRANSLATION_MODEL == config.WIDER_SEARCH_JUDGE_MODEL
    has_openai = bool((os.environ.get("OPENAI_API_KEY") or "").strip())
    if has_openai:
        assert config.TRANSLATION_MODEL == "openai:gpt-5.4"
    else:
        assert config.TRANSLATION_MODEL is None


# -- 2. locale allow-list + resolver -----------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("pl", "pl"),
        ("en", "en"),
        ("PL", "pl"),  # case-insensitive
        ("  pl  ", "pl"),  # whitespace-insensitive
        ("EN", "en"),
        ("xx", "en"),  # unknown → default
        ("de", "en"),  # not (yet) served → default
        ("", "en"),  # empty → default
        (None, "en"),  # missing → default
    ],
)
def test_resolve_locale_allow_list(value: str | None, expected: str) -> None:
    from backend.shared.locale import normalize_locale, resolve_locale

    assert resolve_locale(value) == expected
    assert normalize_locale(value) == expected


def test_is_supported_locale() -> None:
    from backend.shared.locale import SUPPORTED_LOCALES, is_supported_locale

    assert SUPPORTED_LOCALES == frozenset({"en", "pl"})
    assert is_supported_locale("pl") is True
    assert is_supported_locale(" EN ") is True
    assert is_supported_locale("fr") is False
    assert is_supported_locale(None) is False
    assert is_supported_locale("") is False


# -- 3. schema + migration ---------------------------------------------------

_NEW_TABLES = ("content_translations", "guideline_synthesis_translations")


def test_new_tables_declared_on_shared_metadata() -> None:
    """schema.py Core Table + orm.py ORM class both register on the one MetaData,
    and ``create_all`` produces valid DDL for them on SQLite."""
    # Import so the ORM class attaches to the shared metadata.
    import backend.guidelines.orm  # noqa: F401
    from backend.shared.persistence.schema import metadata

    for table in _NEW_TABLES:
        assert table in metadata.tables

    engine = create_engine("sqlite://", future=True)
    metadata.create_all(engine)
    got = set(inspect(engine).get_table_names())
    assert set(_NEW_TABLES) <= got


def test_migration_upgrade_downgrade_upgrade_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Alembic ``e2f9a1c7b4d3`` up → down → up on a throwaway SQLite file.

    The full historical chain cannot run on a fresh DB (later migrations ALTER
    tables the legacy raw-DDL path owns), so we stamp the DB at the prior head
    and exercise only the new revision — the unit under test.
    """
    from alembic.config import Config

    from alembic import command
    from backend import config as app_config
    from backend.shared.persistence import engine as engine_mod

    db_file = tmp_path / "translation_roundtrip.db"
    monkeypatch.setattr(app_config, "DB_URL", f"sqlite:///{db_file}")
    engine_mod.reset_engine_for_tests()

    prior_head = "c1b7a4e8f0d2"
    new_head = "e2f9a1c7b4d3"

    def table_names() -> set[str]:
        return set(inspect(engine_mod.get_engine()).get_table_names())

    try:
        # Build the Config WITHOUT the .ini path: env.py runs ``fileConfig()``
        # only when ``config_file_name`` is set, and that call disables existing
        # loggers process-wide (disable_existing_loggers=True), which would break
        # later logging-assertion tests in the same session. We only need
        # ``script_location`` so alembic can find env.py + the versions.
        cfg = Config()
        cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))

        # Stamp at the prior head so `upgrade head` runs ONLY the new revision.
        command.stamp(cfg, prior_head)

        command.upgrade(cfg, "head")
        assert set(_NEW_TABLES) <= table_names()

        command.downgrade(cfg, "-1")
        after_down = table_names()
        assert not (set(_NEW_TABLES) & after_down)

        command.upgrade(cfg, "head")
        assert set(_NEW_TABLES) <= table_names()

        # Landed on the expected revision.
        from alembic.migration import MigrationContext

        with engine_mod.get_engine().connect() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
        assert current == new_head
    finally:
        engine_mod.reset_engine_for_tests()
