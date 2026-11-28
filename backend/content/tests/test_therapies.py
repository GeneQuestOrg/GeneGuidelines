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


# --- one entry per therapy: base name with and without a qualifier ----------------------


def _row(id: int, name: str, note: str, pmids: tuple[str, ...] = (), sort_order: int = 0) -> Therapy:
    return Therapy(
        id=id,
        disease_slug="fd",
        name=name,
        status="consensus",  # type: ignore[arg-type]
        note=note,
        sort_order=sort_order,
        pmids=pmids,
    )


# GET /api/diseases/fd/therapies on production, 2026-11-28: the six seed rows, then four the therapies finder inserted before it stopped adding names next to a seeded disease's.
_PRODUCTION_FD = [
    _row(1, "Observation (children — standard of care)", "No pain, no functional impairment — monitor until skeletal maturity.", sort_order=10),
    _row(2, "Bisphosphonates (pamidronate, zoledronate)", "Standard for bone pain. IV cycles every 3-6 months.", ("15469225",), sort_order=20),
    _row(3, "Denosumab", "For rapidly progressive lesions.", sort_order=30),
    _row(4, "Burosumab", "Only when FGF23-dependent hypophosphataemia is documented.", sort_order=40),
    _row(5, "Surgery", "Reserved for clinical necessity.", ("16085630", "15469225"), sort_order=50),
    _row(6, "MEK inhibitors", "Preliminary mouse-model data.", sort_order=60),
    _row(7, "Observation", "First-line management for asymptomatic, monostotic lesions.", sort_order=100),
    _row(8, "Surgical correction", "Mainstay for skeletal deformities.", ("16085630", "15469225", "23858622"), sort_order=100),
    _row(9, "Bisphosphonates", "Used to reduce pain and fracture risk.", ("15469225", "99999999"), sort_order=100),
    _row(10, "Cortical grafts", "Preferred graft type for surgical remodeling.", ("16085630",), sort_order=100),
]


def test_fd_production_list_loses_its_two_qualifier_duplicates():
    from backend.content.therapies import merge_qualified_duplicates

    merged = merge_qualified_duplicates(_PRODUCTION_FD)
    assert len(_PRODUCTION_FD) == 10
    assert [t.name for t in merged] == [
        "Observation (children — standard of care)",
        "Bisphosphonates (pamidronate, zoledronate)",
        "Denosumab",
        "Burosumab",
        "Surgery",
        "MEK inhibitors",
        "Surgical correction",
        "Cortical grafts",
    ]


def test_merged_entry_keeps_the_fuller_name_its_note_and_the_union_of_pmids():
    from backend.content.contracts import TherapyResponse
    from backend.content.therapies import merge_qualified_duplicates

    by_name = {t.name: t for t in merge_qualified_duplicates(_PRODUCTION_FD)}
    bisphosphonates = by_name["Bisphosphonates (pamidronate, zoledronate)"]
    assert bisphosphonates.id == 2  # the seed row's id, which its translations are keyed on
    assert bisphosphonates.note == "Standard for bone pain. IV cycles every 3-6 months."
    assert bisphosphonates.pmids == ("15469225", "99999999")
    # Neither observation row cites anything, so the merged one stays unverified.
    observation = TherapyResponse.from_domain(by_name["Observation (children — standard of care)"])
    assert observation.status == "unverified"


def test_a_source_on_the_bare_row_makes_the_merged_entry_sourced():
    from backend.content.contracts import TherapyResponse
    from backend.content.therapies import merge_qualified_duplicates

    rows = [_row(1, "Observation (children)", "seed note"), _row(2, "observation", "finder note", ("12345678",))]
    [merged] = merge_qualified_duplicates(rows)
    assert merged.name == "Observation (children)"
    assert TherapyResponse.from_domain(merged).status == "sourced"


def test_similar_names_and_competing_qualifiers_stay_separate():
    from backend.content.therapies import merge_qualified_duplicates

    rows = [
        _row(1, "Surgery", "a"),
        _row(2, "Surgical correction", "b"),
        _row(3, "MEK inhibitors (trametinib)", "c"),
        _row(4, "MEK inhibitors (selumetinib)", "d"),
        _row(5, "MEK inhibitors", "e"),
    ]
    assert merge_qualified_duplicates(rows) == rows


def test_service_serves_the_merged_list():
    svc = _service(diseases=[_disease("fd")], therapies=_PRODUCTION_FD)
    rows = svc.list_for_disease("fd")
    assert rows is not None
    assert len(rows) == 8
    assert sum(1 for t in rows if t.name.lower().startswith("bisphosphonates")) == 1
