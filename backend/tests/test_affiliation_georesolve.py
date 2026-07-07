"""Tests for the staged affiliation georesolve chain: ROR → Nominatim → Brave+LLM (df-20)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import backend.config as cfg
from backend.flows.doctor_finder import affiliation_georesolve as ag
from backend.flows.doctor_finder import nominatim as nom
from backend.flows.doctor_finder import ror


@pytest.fixture(autouse=True)
def _clear_geo_cache() -> None:
    ag._GEO_RESULT_CACHE.clear()
    yield
    ag._GEO_RESULT_CACHE.clear()


def _disable_free_resolvers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate the paid Brave path by turning off the free ROR + Nominatim stages."""
    monkeypatch.setattr(cfg, "DOCTOR_FINDER_GEO_ROR_ENABLED", False)
    monkeypatch.setattr(cfg, "DOCTOR_FINDER_GEO_NOMINATIM_ENABLED", False)


def _article_with_unresolved_affiliation(raw: str) -> dict:
    return {
        "pmid": "1",
        "title": "t",
        "authors": [
            {
                "last_name": "Doe",
                "fore_name": "Jane",
                "parsed_affiliation": {
                    "raw": raw,
                    "institution": "National Institutes of Health",
                    "city": "Bethesda",
                    "country_name": None,
                    "country_code": None,
                    "continent": None,
                },
            }
        ],
    }


def test_georesolve_skips_when_no_resolver_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """No Brave key AND both free resolvers off => nothing resolved, step is a no-op."""
    _disable_free_resolvers(monkeypatch)
    monkeypatch.setattr(cfg, "BRAVE_API_KEY", None)
    ctx = {"articles": [_article_with_unresolved_affiliation("National Institutes of Health, Bethesda, MD, USA campus")]}
    out = asyncio.run(ag.run_async(ctx))
    assert out["articles"][0]["authors"][0]["parsed_affiliation"]["country_code"] is None


def test_georesolve_applies_high_confidence_us(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_free_resolvers(monkeypatch)
    monkeypatch.setattr(cfg, "BRAVE_API_KEY", "test-subscription-token")
    monkeypatch.setattr(ag, "brave_web_search", AsyncMock(return_value=[{"title": "NIH", "url": "https://nih.gov", "description": "Bethesda Maryland United States"}]))
    with patch(
        "backend.flows.doctor_finder.affiliation_georesolve.run_llm_simple_async",
        new=AsyncMock(return_value={"country_iso2": "US", "confidence": 0.92, "rationale": "1"}),
    ):
        raw = "National Institutes of Health, Bethesda, MD, USA campus"
        ctx = {"articles": [_article_with_unresolved_affiliation(raw)]}
        out = asyncio.run(ag.run_async(ctx))
    pa = out["articles"][0]["authors"][0]["parsed_affiliation"]
    assert pa["country_code"] == "US"
    assert pa["continent"] == "North America"
    assert pa["geo_source"] == "brave_web_llm"
    assert pa["geo_confidence"] == pytest.approx(0.92)


def test_georesolve_rejects_low_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_free_resolvers(monkeypatch)
    monkeypatch.setattr(cfg, "BRAVE_API_KEY", "test-subscription-token")
    monkeypatch.setattr(ag, "brave_web_search", AsyncMock(return_value=[{"title": "x", "url": "https://x", "description": "y"}]))
    with patch(
        "backend.flows.doctor_finder.affiliation_georesolve.run_llm_simple_async",
        new=AsyncMock(return_value={"country_iso2": "US", "confidence": 0.4, "rationale": "uncertain"}),
    ):
        raw = "National Institutes of Health, Bethesda, MD, USA campus"
        ctx = {"articles": [_article_with_unresolved_affiliation(raw)]}
        out = asyncio.run(ag.run_async(ctx))
    assert out["articles"][0]["authors"][0]["parsed_affiliation"]["country_code"] is None


def test_brave_skips_llm_when_no_web_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    """No Brave snippets (empty result / 429) => the LLM must NOT be called (no retry-storm)."""
    _disable_free_resolvers(monkeypatch)
    monkeypatch.setattr(cfg, "BRAVE_API_KEY", "test-subscription-token")
    monkeypatch.setattr(ag, "brave_web_search", AsyncMock(return_value=[]))
    llm = AsyncMock(return_value={"country_iso2": "US", "confidence": 0.99, "rationale": "x"})
    with patch("backend.flows.doctor_finder.affiliation_georesolve.run_llm_simple_async", new=llm):
        raw = "National Institutes of Health, Bethesda, MD, USA campus"
        ctx = {"articles": [_article_with_unresolved_affiliation(raw)]}
        out = asyncio.run(ag.run_async(ctx))
    assert out["articles"][0]["authors"][0]["parsed_affiliation"]["country_code"] is None
    assert llm.await_count == 0


def test_ror_resolves_before_brave_is_touched(monkeypatch: pytest.MonkeyPatch) -> None:
    """ROR is the primary resolver: a confident ROR hit must short-circuit before Brave/LLM."""
    monkeypatch.setattr(cfg, "DOCTOR_FINDER_GEO_ROR_ENABLED", True)
    monkeypatch.setattr(cfg, "DOCTOR_FINDER_GEO_NOMINATIM_ENABLED", False)
    monkeypatch.setattr(cfg, "BRAVE_API_KEY", "test-subscription-token")  # key present but must NOT be used
    monkeypatch.setattr(
        ror,
        "lookup_affiliation_country",
        AsyncMock(return_value=ror.RorMatch(country_code="CN", country_name="China", city="Beijing", score=1.0)),
    )
    # Brave must never be called; make it explode if it is.
    monkeypatch.setattr(ag, "brave_web_search", AsyncMock(side_effect=AssertionError("Brave must not run when ROR resolves")))
    ctx = {"articles": [_article_with_unresolved_affiliation("Beijing Children's Hospital, Department of Orthopedics")]}
    out = asyncio.run(ag.run_async(ctx))
    pa = out["articles"][0]["authors"][0]["parsed_affiliation"]
    assert pa["country_code"] == "CN"
    assert pa["continent"] == "Asia"
    assert pa["geo_source"] == "ror"


def test_nominatim_used_when_ror_fails_and_no_brave_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ROR is unsure and there is no Brave key, Nominatim (free) still fills the country."""
    monkeypatch.setattr(cfg, "DOCTOR_FINDER_GEO_ROR_ENABLED", True)
    monkeypatch.setattr(cfg, "DOCTOR_FINDER_GEO_NOMINATIM_ENABLED", True)
    monkeypatch.setattr(cfg, "DOCTOR_FINDER_GEO_NOMINATIM_MAX_LOOKUPS", 10)
    monkeypatch.setattr(cfg, "DOCTOR_FINDER_GEO_NOMINATIM_MIN_INTERVAL_SEC", 1.0)
    monkeypatch.setattr(cfg, "BRAVE_API_KEY", None)
    monkeypatch.setattr(ror, "lookup_affiliation_country", AsyncMock(return_value=None))
    monkeypatch.setattr(nom, "lookup_affiliation_country", AsyncMock(return_value=nom.NominatimMatch(country_code="DE", city="Berlin")))
    # Skip the real 1s sleep so the test stays fast.
    monkeypatch.setattr(ag.asyncio, "sleep", AsyncMock(return_value=None))
    ctx = {"articles": [_article_with_unresolved_affiliation("Charite Universitaetsmedizin, Klinik fuer Orthopaedie")]}
    out = asyncio.run(ag.run_async(ctx))
    pa = out["articles"][0]["authors"][0]["parsed_affiliation"]
    assert pa["country_code"] == "DE"
    assert pa["continent"] == "Europe"
    assert pa["geo_source"] == "nominatim"


def test_ror_pick_chosen_ignores_non_chosen_and_low_score() -> None:
    """ROR helper must trust only ``chosen`` matches above the score floor (NIH→Malaysia guard)."""
    items = [
        {"chosen": False, "score": 1.0, "organization": {"locations": [{"geonames_details": {"country_code": "MY"}}]}},
        {"chosen": True, "score": 0.5, "organization": {"locations": [{"geonames_details": {"country_code": "US"}}]}},
    ]
    # chosen item is below min_score => refuse rather than risk a wrong country.
    assert ror._pick_chosen(items, min_score=0.9) is None

    good = [{"chosen": True, "score": 1.0, "organization": {"id": "x", "locations": [{"geonames_details": {"country_code": "CN", "country_name": "China", "name": "Beijing"}}]}}]
    m = ror._pick_chosen(good, min_score=0.9)
    assert m is not None and m.country_code == "CN" and m.city == "Beijing"


def test_apply_patches_uses_second_affiliation_line_when_only_that_line_gets_geo() -> None:
    """Parser keeps first line as ``parsed_affiliation.raw`` when no line has ISO2; geo may resolve a later line."""
    line1 = "Metabolic Bone Disorders Unit, University Department of Medicine"
    line2 = "Laboratory of Musculoskeletal Disorders, NIH campus, Bethesda"
    articles = [
        {
            "pmid": "9",
            "title": "t",
            "authors": [
                {
                    "affiliations_raw": [line1, line2],
                    "parsed_affiliation": {
                        "raw": line1,
                        "institution": line1.split(",")[0].strip(),
                        "city": None,
                        "country_name": None,
                        "country_code": None,
                        "continent": None,
                    },
                }
            ],
        }
    ]
    patch = ag._patch_from_iso2("US", 0.91)
    key2 = ag._cache_key(line2)
    out = ag._apply_patches(articles, {key2: patch})
    pa = out[0]["authors"][0]["parsed_affiliation"]
    assert pa["country_code"] == "US"
    assert pa["raw"] == line2
    assert pa["geo_source"] == "brave_web_llm"


def test_brave_stage_respects_paid_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with many unresolved affiliations, the PAID Brave stage runs at most max_lookups times."""
    _disable_free_resolvers(monkeypatch)
    monkeypatch.setattr(cfg, "BRAVE_API_KEY", "test-subscription-token")
    monkeypatch.setattr(cfg, "DOCTOR_FINDER_GEO_BRAVE_MAX_LOOKUPS", 1)
    brave = AsyncMock(return_value=[{"title": "x", "url": "https://x", "description": "United States"}])
    monkeypatch.setattr(ag, "brave_web_search", brave)

    def _article(pmid: str, raw: str) -> dict:
        return {
            "pmid": pmid,
            "title": "t",
            "authors": [
                {
                    "last_name": "Doe",
                    "fore_name": pmid,
                    "parsed_affiliation": {
                        "raw": raw,
                        "institution": raw.split(",")[0],
                        "city": None,
                        "country_name": None,
                        "country_code": None,
                        "continent": None,
                    },
                }
            ],
        }

    ctx = {
        "articles": [
            _article("1", "Alpha Institute, Cityone"),
            _article("2", "Beta Institute, Citytwo"),
        ]
    }
    with patch(
        "backend.flows.doctor_finder.affiliation_georesolve.run_llm_simple_async",
        new=AsyncMock(return_value={"country_iso2": "US", "confidence": 0.92, "rationale": "1"}),
    ):
        out = asyncio.run(ag.run_async(ctx))

    codes = [a["authors"][0]["parsed_affiliation"]["country_code"] for a in out["articles"]]
    assert codes.count("US") == 1
    assert codes.count(None) == 1
    assert brave.await_count == 1


def test_collect_tasks_orders_by_global_frequency() -> None:
    """Common unresolved affiliation strings should rank before rare ones within the cap."""
    common = "National Institutes of Health, Bethesda, Maryland"
    rare = "Obscure Institute Alpha Seven, Nowhereville"
    arts = [
        {
            "authors": [
                {
                    "affiliations_raw": [common],
                    "parsed_affiliation": {
                        "raw": common,
                        "institution": "NIH",
                        "country_code": None,
                    },
                }
            ]
        },
        {
            "authors": [
                {
                    "affiliations_raw": [common],
                    "parsed_affiliation": {
                        "raw": common,
                        "institution": "NIH",
                        "country_code": None,
                    },
                }
            ]
        },
        {
            "authors": [
                {
                    "affiliations_raw": [rare],
                    "parsed_affiliation": {
                        "raw": rare,
                        "institution": "Obscure",
                        "country_code": None,
                    },
                }
            ]
        },
    ]
    tasks = ag._collect_tasks(arts)
    keys = [t[0] for t in tasks]
    assert keys[0] == ag._cache_key(common)
    assert ag._cache_key(rare) in keys
