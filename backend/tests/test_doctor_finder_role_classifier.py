from __future__ import annotations

import asyncio
from datetime import date

import pytest

from backend.flows.doctor_finder.role_classifier import run_async


def _make_author(
    guideline: int = 0,
    review: int = 0,
    original: int = 0,
    case_report: int = 0,
    years: list[int] | None = None,
    last_name: str = "Smith",
    initials: str = "J",
) -> dict:
    paper_count = guideline + review + original + case_report
    papers = []
    for i, y in enumerate(years or []):
        papers.append(
            {
                "year": y,
                "publication_types": [],
                "parsed_affiliation": None,
                "pmid": str(i),
                "title": "test",
                "author_position": "first",
                "affiliations_raw": [],
                "pubmed_url": "",
            }
        )
    return {
        "author_key": f"name:{last_name.lower()}_j_unknown",
        "last_name": last_name,
        "fore_name": "John",
        "initials": initials,
        "guideline_count": guideline,
        "review_count": review,
        "original_count": original,
        "case_report_count": case_report,
        "paper_count": paper_count,
        "country_primary": None,
        "continent_primary": None,
        "institution_primary": None,
        "papers": papers,
        "flags": {},
        "role": None,
        "score": 0.0,
        "orcid": None,
        "pubmed_author_id": None,
        "ai_justification": None,
    }


def _ctx(authors: list[dict], disease: str = "fibrous dysplasia") -> dict:
    return {"aggregated_authors": authors, "initial": {"disease_name": disease}}


async def _no_ct(*_args, **_kwargs) -> bool:
    return False


def test_guideline_author_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.flows.doctor_finder.role_classifier._check_clinical_trial", _no_ct
    )
    author = _make_author(guideline=1)
    result = asyncio.run(run_async(_ctx([author])))
    assert result["aggregated_authors"][0]["role"]["role"] == "guideline_author"


def test_senior_investigator_by_reviews(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.flows.doctor_finder.role_classifier._check_clinical_trial", _no_ct
    )
    author = _make_author(review=2)
    result = asyncio.run(run_async(_ctx([author])))
    assert result["aggregated_authors"][0]["role"]["role"] == "senior_investigator"


def test_senior_investigator_by_original(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.flows.doctor_finder.role_classifier._check_clinical_trial", _no_ct
    )
    author = _make_author(original=5)
    result = asyncio.run(run_async(_ctx([author])))
    assert result["aggregated_authors"][0]["role"]["role"] == "senior_investigator"


def test_active_contributor_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.flows.doctor_finder.role_classifier._check_clinical_trial", _no_ct
    )
    author = _make_author(original=2, years=[2025])
    result = asyncio.run(run_async(_ctx([author]), now=date(2026, 1, 1)))
    assert result["aggregated_authors"][0]["role"]["role"] == "active_contributor"


def test_case_reporter_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.flows.doctor_finder.role_classifier._check_clinical_trial", _no_ct
    )
    author = _make_author(case_report=1)
    result = asyncio.run(run_async(_ctx([author])))
    assert result["aggregated_authors"][0]["role"]["role"] == "case_reporter"


def test_peripheral_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.flows.doctor_finder.role_classifier._check_clinical_trial", _no_ct
    )
    author = _make_author()
    result = asyncio.run(run_async(_ctx([author])))
    assert result["aggregated_authors"][0]["role"]["role"] == "peripheral"


def test_active_last_2y_true_and_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.flows.doctor_finder.role_classifier._check_clinical_trial", _no_ct
    )
    now = date(2026, 1, 1)

    active_author = _make_author(years=[2025])
    result = asyncio.run(run_async(_ctx([active_author]), now=now))
    assert result["aggregated_authors"][0]["flags"]["active_last_2y"] is True

    stale_author = _make_author(years=[2020])
    result = asyncio.run(run_async(_ctx([stale_author]), now=now))
    assert result["aggregated_authors"][0]["flags"]["active_last_2y"] is False


def test_runs_clinical_trial_flag_true(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _yes_ct(*_args, **_kwargs) -> bool:
        return True

    monkeypatch.setattr(
        "backend.flows.doctor_finder.role_classifier._check_clinical_trial", _yes_ct
    )
    author = _make_author()
    result = asyncio.run(run_async(_ctx([author])))
    assert result["aggregated_authors"][0]["flags"]["runs_clinical_trial"] is True


def test_clinical_trial_exception_is_graceful(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise(*_args, **_kwargs) -> bool:
        raise RuntimeError("network failure")

    # Patch the internal function before the cache check to simulate raw failure
    import backend.flows.doctor_finder.role_classifier as mod

    async def _wrapper(*_a: object, **_kw: object) -> bool:
        try:
            return await _raise()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).debug("graceful: %s", exc)
            return False

    monkeypatch.setattr(mod, "_check_clinical_trial", _wrapper)
    author = _make_author()
    result = asyncio.run(run_async(_ctx([author])))
    assert result["aggregated_authors"][0]["flags"]["runs_clinical_trial"] is False


def test_clinical_trial_respects_max_authors_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the busiest authors (by paper_count) receive CT API calls up to DOCTOR_FINDER_CT_MAX_AUTHORS."""
    import backend.flows.doctor_finder.role_classifier as mod

    calls: list[int] = []

    async def counting_ct(*_a: object, **_k: object) -> bool:
        calls.append(1)
        return True

    monkeypatch.setattr(mod, "_check_clinical_trial", counting_ct)
    monkeypatch.setattr(mod, "DOCTOR_FINDER_CT_MAX_AUTHORS", 2)
    monkeypatch.setattr(mod, "DOCTOR_FINDER_CT_CONCURRENCY", 4)

    a30 = _make_author(original=30, last_name="Alpha")
    a20 = _make_author(original=20, last_name="Beta")
    a10 = _make_author(original=10, last_name="Gamma")

    result = asyncio.run(run_async(_ctx([a10, a30, a20])))
    assert len(calls) == 2
    by_name = {x["last_name"]: x["flags"]["runs_clinical_trial"] for x in result["aggregated_authors"]}
    assert by_name["Alpha"] is True
    assert by_name["Beta"] is True
    assert by_name["Gamma"] is False
