"""Unit tests for the foundation service using in-memory repositories."""

from __future__ import annotations

import pytest

from backend.content.foundations import (
    Foundation,
    FoundationService,
    InMemoryFoundationRepo,
)
from backend.content.models import Disease
from backend.content.repository import InMemoryDiseaseRepo


def _disease(slug: str) -> Disease:
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


def _foundation(
    *,
    id: int,
    name: str,
    diseases: tuple[str, ...],
    scope: str = "International",
) -> Foundation:
    return Foundation(
        id=id,
        name=name,
        scope=scope,
        url="example.org",
        city=None,
        country=None,
        services=(),
        diseases=diseases,
    )


def _service(*, diseases, foundations) -> FoundationService:
    return FoundationService(
        foundation_repo=InMemoryFoundationRepo(foundations),
        disease_repo=InMemoryDiseaseRepo(diseases),
    )


def test_list_for_disease_filters_by_m2m_membership():
    svc = _service(
        diseases=[_disease("fd"), _disease("noonan")],
        foundations=[
            _foundation(id=1, name="FDMAS Alliance", diseases=("fd", "mas")),
            _foundation(id=2, name="GeneQuest", diseases=("fd", "mas", "noonan")),
            _foundation(id=3, name="Team Noonan", diseases=("noonan",)),
        ],
    )
    fd = svc.list_for_disease("fd")
    assert fd is not None
    assert sorted(f.name for f in fd) == ["FDMAS Alliance", "GeneQuest"]


def test_list_for_disease_returns_none_for_unknown_slug():
    svc = _service(diseases=[_disease("fd")], foundations=[])
    assert svc.list_for_disease("nope") is None


def test_list_for_disease_normalises_case():
    svc = _service(
        diseases=[_disease("fd")],
        foundations=[_foundation(id=1, name="A", diseases=("fd",))],
    )
    assert svc.list_for_disease("FD") is not None


def test_list_all_sorts_by_name():
    svc = _service(
        diseases=[],
        foundations=[
            _foundation(id=1, name="Zebra", diseases=()),
            _foundation(id=2, name="Alpha", diseases=()),
        ],
    )
    assert [f.name for f in svc.list_all()] == ["Alpha", "Zebra"]
