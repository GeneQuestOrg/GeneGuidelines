"""Service-level tests for the disease vertical.

These exercise the full :class:`backend.content.service.DiseaseService` /
:class:`backend.content.repository.InMemoryDiseaseRepo` stack without
touching SQLite, FastAPI, or any other framework piece. They prove the
``Protocol`` boundary works in isolation and pin the search/normalisation
contract down with cheap, fast assertions.
"""

from __future__ import annotations

import pytest

from backend.content.models import Disease
from backend.content.repository import InMemoryDiseaseRepo
from backend.content.service import DiseaseService


def _fixture_repo() -> InMemoryDiseaseRepo:
    return InMemoryDiseaseRepo(
        [
            Disease(
                slug="fd",
                name="Fibrous dysplasia",
                name_short="FD",
                omim="174800",
                gene="GNAS",
                inheritance="somatic mosaic",
                summary="Bone disorder caused by post-zygotic GNAS mutations.",
                prevalence_text="ultra-rare",
                status="ai-draft",
                coverage="full",
                accent="teal",
                doctors_count=12,
            ),
            Disease(
                slug="mas",
                name="McCune–Albright syndrome",
                name_short="MAS",
                omim="174800",
                gene="GNAS",
                inheritance="somatic mosaic",
                summary="Fibrous dysplasia plus endocrinopathies and café-au-lait spots.",
                prevalence_text="ultra-rare",
                status="skeleton",
                coverage="skeleton",
                accent="amber",
                doctors_count=4,
            ),
            Disease(
                slug="noonan",
                name="Noonan syndrome",
                name_short="Noonan",
                omim="163950",
                gene="PTPN11",
                inheritance="autosomal dominant",
                summary="RASopathy with characteristic facial features and cardiac involvement.",
                prevalence_text="1 in 1,000-2,500",
                status="skeleton",
                coverage="skeleton",
                accent="indigo",
                doctors_count=0,
            ),
        ]
    )


def _service(doctor_counts: dict[str, int] | None = None) -> DiseaseService:
    counts = doctor_counts or {}

    def provider(slug: str) -> int:
        return counts.get(slug, 0)

    return DiseaseService(repo=_fixture_repo(), doctor_count=provider)


def test_list_returns_all_diseases_sorted_by_name() -> None:
    service = _service()

    items = service.list()

    assert [d.slug for d in items] == ["fd", "mas", "noonan"]


def test_list_filters_case_insensitively_on_name() -> None:
    service = _service()

    # "noonan" matches the Noonan-syndrome row only — distinct enough that
    # the substring won't bleed into FD/MAS summaries.
    assert [d.slug for d in service.list(query="noonan")] == ["noonan"]
    assert [d.slug for d in service.list(query="NOONAN")] == ["noonan"]


def test_list_filters_on_gene_symbol() -> None:
    service = _service()

    assert {d.slug for d in service.list(query="gnas")} == {"fd", "mas"}


def test_list_filters_on_slug() -> None:
    service = _service()

    assert [d.slug for d in service.list(query="noonan")] == ["noonan"]


def test_list_returns_all_when_query_is_whitespace() -> None:
    service = _service()

    assert len(service.list(query="   ")) == 3


def test_get_returns_disease_for_known_slug() -> None:
    service = _service()

    disease = service.get("fd")

    assert disease is not None
    assert disease.gene == "GNAS"


def test_get_returns_none_for_unknown_slug() -> None:
    service = _service()

    assert service.get("does-not-exist") is None


@pytest.mark.parametrize("bad", ["", " ", "BAD!slug", "1bad", "way-too-long-" + "x" * 80])
def test_get_returns_none_for_malformed_slug(bad: str) -> None:
    service = _service()

    assert service.get(bad) is None


def test_live_doctor_count_overrides_row_value() -> None:
    service = _service({"fd": 42})

    fd = service.get("fd")

    assert fd is not None
    assert fd.doctors_count == 42


def test_live_doctor_count_falls_back_silently_on_provider_error() -> None:
    def boom(_slug: str) -> int:
        raise RuntimeError("doctor catalog down")

    service = DiseaseService(repo=_fixture_repo(), doctor_count=boom)

    fd = service.get("fd")

    assert fd is not None
    assert fd.doctors_count == 12  # row-level fallback
