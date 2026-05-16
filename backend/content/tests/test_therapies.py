"""Unit tests for the therapy service via the in-memory implementations."""

from __future__ import annotations

import pytest

from backend.content.models import Disease
from backend.content.repository import InMemoryDiseaseRepo
from backend.content.therapies import (
    InMemoryTherapyRepo,
    Therapy,
    TherapyService,
)


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


def _therapy(
    *,
    id: int,
    slug: str,
    name: str,
    status: str = "consensus",
    sort_order: int = 100,
) -> Therapy:
    return Therapy(
        id=id,
        disease_slug=slug,
        name=name,
        status=status,  # type: ignore[arg-type]
        note="",
        sort_order=sort_order,
    )


def _service(*, diseases, therapies) -> TherapyService:
    return TherapyService(
        therapy_repo=InMemoryTherapyRepo(therapies),
        disease_repo=InMemoryDiseaseRepo(diseases),
    )


def test_list_for_disease_returns_only_that_diseases_therapies():
    svc = _service(
        diseases=[_disease("fd"), _disease("mas")],
        therapies=[
            _therapy(id=1, slug="fd", name="Pamidronate"),
            _therapy(id=2, slug="mas", name="Letrozole"),
            _therapy(id=3, slug="fd", name="Denosumab"),
        ],
    )
    fd = svc.list_for_disease("fd")
    assert fd is not None
    assert sorted(t.name for t in fd) == ["Denosumab", "Pamidronate"]


def test_list_for_disease_returns_none_for_unknown():
    svc = _service(diseases=[_disease("fd")], therapies=[])
    assert svc.list_for_disease("noonan") is None


def test_list_for_disease_orders_by_sort_then_id():
    svc = _service(
        diseases=[_disease("fd")],
        therapies=[
            _therapy(id=3, slug="fd", name="C", sort_order=10),
            _therapy(id=2, slug="fd", name="B", sort_order=10),
            _therapy(id=1, slug="fd", name="A", sort_order=5),
        ],
    )
    rows = svc.list_for_disease("fd")
    assert [t.name for t in rows] == ["A", "B", "C"]  # type: ignore[union-attr]
