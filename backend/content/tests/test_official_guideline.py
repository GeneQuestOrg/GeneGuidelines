"""Unit tests for the official-guideline pointer service."""

from __future__ import annotations

import pytest

from backend.content.models import Disease
from backend.content.official_guideline import (
    InMemoryOfficialGuidelineRepo,
    OfficialGuideline,
    OfficialGuidelineService,
)
from backend.content.repository import InMemoryDiseaseRepo


def _disease(slug: str = "fd") -> Disease:
    return Disease(
        slug=slug,
        name=slug.upper(),
        name_short=slug.upper(),
        omim="0",
        gene="G",
        inheritance="x",
        summary="",
        prevalence_text="",
        status="consensus",
        coverage="full",
        accent="teal",
    )


def _service(*, pointers=()) -> OfficialGuidelineService:
    return OfficialGuidelineService(
        repo=InMemoryOfficialGuidelineRepo(pointers),
        disease_repo=InMemoryDiseaseRepo([_disease("fd")]),
    )


def _pointer(**overrides) -> OfficialGuideline:
    base = dict(
        disease_slug="fd",
        title="Best practice management guidelines for FD/MAS",
        authors="Javaid et al.",
        year=2019,
        journal="Orphanet J Rare Dis",
        pmid="31196103",
        url="https://link.springer.com/article/10.1186/s13023-019-1102-9",
        summary="International consensus.",
        confirmed_by="GeneQuest reviewer panel",
        confirmed_at="2026-05-17",
        source="seed",
    )
    base.update(overrides)
    return OfficialGuideline(**base)  # type: ignore[arg-type]


def test_get_returns_none_for_unknown_disease():
    svc = _service()
    assert svc.get("noonan") is None


def test_get_returns_none_for_malformed_slug():
    svc = _service()
    assert svc.get("../../etc/passwd") is None


def test_get_returns_seeded_pointer():
    svc = _service(pointers=[_pointer()])
    out = svc.get("fd")
    assert out is not None
    assert out.pmid == "31196103"
    assert out.source == "seed"


def test_confirm_upserts_reviewer_source():
    svc = _service()
    out = svc.confirm(
        slug="fd",
        title="Updated paper",
        authors="Other",
        year=2025,
        journal="JBMR",
        pmid="99999999",
        confirmed_by="Dr. Reviewer",
    )
    assert out is not None
    assert out.source == "reviewer"
    assert out.pmid == "99999999"
    # And the next get returns the upserted row, not the previous (none).
    second = svc.get("fd")
    assert second is not None and second.pmid == "99999999"


def test_confirm_returns_none_for_unknown_disease():
    svc = _service()
    out = svc.confirm(
        slug="noonan",
        title="X",
        authors="Y",
        year=2020,
        journal="Z",
        pmid="1",
        confirmed_by="A",
    )
    assert out is None


def test_confirm_overwrites_existing_seed():
    svc = _service(pointers=[_pointer(source="seed")])
    out = svc.confirm(
        slug="fd",
        title="New consensus",
        authors="Updated authors",
        year=2026,
        journal="Lancet",
        pmid="40000000",
        confirmed_by="Dr. Reviewer",
        source="reviewer",
    )
    assert out is not None
    assert out.source == "reviewer"
    assert out.pmid == "40000000"
    # The seed entry is replaced, not duplicated.
    assert svc.get("fd").pmid == "40000000"  # type: ignore[union-attr]
