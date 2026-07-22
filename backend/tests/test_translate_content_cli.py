"""Unit tests for the PR5 backfill CLI (``backend.scripts.translate_content``).

The PR2 worker is mocked, so no database or model is touched — we assert only the
CLI's argv parsing (slugs + ``--locale``) and its slug resolution / worker fan-out
(no-slug → every listed catalog slug, via an injected in-memory disease repo).
"""

from __future__ import annotations

import asyncio

import pytest

from backend.content.models import Disease
from backend.content.repository import InMemoryDiseaseRepo
from backend.scripts import translate_content as cli


def _disease(slug: str, name: str, *, listed: bool = True) -> Disease:
    return Disease(
        slug=slug,
        name=name,
        name_short=name[:3],
        omim="000000",
        gene="G",
        inheritance="somatic",
        summary="summary",
        prevalence_text="rare",
        status="draft",
        coverage="full",
        accent="teal",
        listed=listed,
    )


# --------------------------------------------------------------------------- #
#  argv parsing                                                               #
# --------------------------------------------------------------------------- #


def test_parse_args_no_slugs_no_locale() -> None:
    assert cli._parse_args([]) == ([], None)


def test_parse_args_slugs_only() -> None:
    assert cli._parse_args(["fd", "mas"]) == (["fd", "mas"], None)


def test_parse_args_locale_space_separated() -> None:
    slugs, locales = cli._parse_args(["fd", "--locale", "pl,de"])
    assert slugs == ["fd"]
    assert locales == ["pl", "de"]


def test_parse_args_locale_equals_form_and_normalises() -> None:
    slugs, locales = cli._parse_args(["--locales=PL, De ,,", "fd"])
    assert slugs == ["fd"]
    assert locales == ["pl", "de"]  # trimmed, lowercased, blanks dropped


def test_parse_args_unknown_flag_raises() -> None:
    with pytest.raises(SystemExit):
        cli._parse_args(["--bogus"])


# --------------------------------------------------------------------------- #
#  slug resolution                                                            #
# --------------------------------------------------------------------------- #


def test_resolve_slugs_explicit_bypasses_catalog() -> None:
    repo = InMemoryDiseaseRepo([_disease("fd", "Fibrous Dysplasia")])
    assert cli._resolve_slugs(["mas", "noonan"], repo) == ["mas", "noonan"]


def test_resolve_slugs_no_slug_uses_listed_catalog() -> None:
    repo = InMemoryDiseaseRepo(
        [
            _disease("fd", "Fibrous Dysplasia"),
            _disease("mas", "McCune-Albright"),
            _disease("hidden", "Unlisted", listed=False),
        ]
    )
    # Only listed diseases, name-sorted (InMemoryDiseaseRepo.list_all contract).
    assert cli._resolve_slugs([], repo) == ["fd", "mas"]


# --------------------------------------------------------------------------- #
#  worker fan-out (worker mocked)                                             #
# --------------------------------------------------------------------------- #


def _patch_worker(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str] | None]]:
    calls: list[tuple[str, list[str] | None]] = []

    async def _fake(slug, locales=None, **kwargs):
        calls.append((slug, locales))
        return {
            "slug": slug,
            "status": "ok",
            "model": "openai:gpt-5.4",
            "locales_requested": locales or ["pl"],
            "results": {},
            "counts": {"translated": 1, "fresh": 0, "empty": 0, "failed": 0},
        }

    monkeypatch.setattr(cli, "translate_disease_content", _fake)
    return calls


def test_run_no_slug_fans_out_to_every_catalog_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_worker(monkeypatch)
    repo = InMemoryDiseaseRepo(
        [_disease("fd", "Fibrous Dysplasia"), _disease("mas", "McCune-Albright")]
    )

    rc = asyncio.run(cli.run([], None, disease_repo=repo))

    assert rc == 0
    assert [slug for slug, _ in calls] == ["fd", "mas"]
    # No --locale → worker invoked with None (falls back to TRANSLATION_TARGET_LOCALES).
    assert all(locales is None for _, locales in calls)


def test_run_passes_locale_override_to_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_worker(monkeypatch)

    rc = asyncio.run(cli.run(["fd"], ["pl", "de"]))

    assert rc == 0
    assert calls == [("fd", ["pl", "de"])]


def test_main_wires_argv_through_to_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_worker(monkeypatch)

    rc = cli.main(["translate_content", "fd", "--locale", "de"])

    assert rc == 0
    assert calls == [("fd", ["de"])]
