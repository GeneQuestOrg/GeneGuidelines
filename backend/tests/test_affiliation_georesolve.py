"""Tests for Brave + LLM affiliation georesolve (df-20)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import backend.config as cfg
from backend.flows.doctor_finder import affiliation_georesolve as ag


@pytest.fixture(autouse=True)
def _clear_geo_cache() -> None:
    ag._GEO_RESULT_CACHE.clear()
    yield
    ag._GEO_RESULT_CACHE.clear()


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


def test_georesolve_skips_when_no_brave_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "BRAVE_API_KEY", None)
    ctx = {"articles": [_article_with_unresolved_affiliation("National Institutes of Health, Bethesda, MD, USA campus")]}
    out = asyncio.run(ag.run_async(ctx))
    assert out["articles"][0]["authors"][0]["parsed_affiliation"]["country_code"] is None


def test_georesolve_applies_high_confidence_us(monkeypatch: pytest.MonkeyPatch) -> None:
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
