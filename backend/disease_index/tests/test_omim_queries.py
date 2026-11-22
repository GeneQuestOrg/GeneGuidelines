"""OMIM-number queries are answered from the local index, never guessed by a model.

In the FD model experiment (November 2026) no model recognised "OMIM 174800"; one confidently answered Tay-Sachs. The index already holds OMIM numbers as exact aliases, so both the autocomplete and the wider search look the number up there first.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.content.repository import InMemoryDiseaseRepo
from backend.disease_index.models import DiseaseAlias, DiseaseIndexEntry
from backend.disease_index.omim import omim_number
from backend.disease_index.repository import InMemoryDiseaseIndexRepo, normalize_term
from backend.disease_index.service import (
    LOCAL_INDEX_MODEL,
    DiseaseSuggestionService,
    WiderDiseaseSearchService,
)


def _mas() -> DiseaseIndexEntry:
    name = "McCune-Albright Syndrome"
    return DiseaseIndexEntry(
        primary_id="ORPHA:562",
        source="manual",
        canonical_name=name,
        canonical_name_norm=normalize_term(name),
        category="genetic",
        is_in_scope=True,
        inheritance=None,
        summary="",
        omim_codes=("174800",),
        gene_symbols=("GNAS",),
        local_slug="mas",
        refreshed_at="2026-01-01T00:00:00Z",
        aliases=(
            DiseaseAlias(alias=name, alias_norm=normalize_term(name), kind="canonical", weight=1.6),
            DiseaseAlias(alias="174800", alias_norm="174800", kind="omim"),
        ),
    )


@pytest.mark.parametrize(
    "query",
    ["174800", "#174800", "OMIM 174800", "OMIM:174800", "omim: #174800", "MIM 174800", "OMIM174800", "  OMIM 174800 "],
)
def test_recognises_the_shapes_people_paste(query: str) -> None:
    assert omim_number(query) == "174800"


@pytest.mark.parametrize("query", ["", "fibrous dysplasia", "17480", "1748001", "OMIM", "GNAS 174800", "174800 GNAS"])
def test_anything_else_is_not_an_omim_query(query: str) -> None:
    assert omim_number(query) is None


@pytest.mark.parametrize("query", ["OMIM 174800", "OMIM:174800", "174800"])
def test_autocomplete_finds_the_disease_by_its_omim_number(query: str) -> None:
    svc = DiseaseSuggestionService(
        repo=InMemoryDiseaseIndexRepo(seed=[_mas()]),
        disease_repo=InMemoryDiseaseRepo(),
    )
    hits = svc.suggest(query)
    assert [hit.entry.primary_id for hit in hits][:1] == ["ORPHA:562"]


def test_wider_search_answers_an_omim_number_from_the_index_without_a_model() -> None:
    calls: list[str] = []

    async def lookup(query: str) -> object:
        calls.append(query)
        raise AssertionError("the model must not be asked about an OMIM number the index knows")

    svc = WiderDiseaseSearchService(lookup=lookup, index=InMemoryDiseaseIndexRepo(seed=[_mas()]))
    result = asyncio.run(svc.search("OMIM 174800"))

    assert calls == []
    assert result.model_used == LOCAL_INDEX_MODEL
    assert result.judged is False
    assert [c.canonical_name for c in result.candidates] == ["McCune-Albright Syndrome"]
    candidate = result.candidates[0]
    assert candidate.omim == "174800"
    assert candidate.gene == "GNAS"
    assert candidate.is_in_scope is True
    assert "ORPHA:562" in candidate.evidence


def test_wider_search_falls_back_to_the_models_when_the_index_does_not_know_the_number() -> None:
    calls: list[str] = []

    class _Identification:
        candidates: list[object] = []
        notes = "not found"
        judged = True
        judge_model = "anthropic:claude-sonnet-5-5"
        generator_model = ""

    async def lookup(query: str) -> object:
        calls.append(query)
        return _Identification()

    svc = WiderDiseaseSearchService(lookup=lookup, index=InMemoryDiseaseIndexRepo(seed=[_mas()]))
    result = asyncio.run(svc.search("OMIM 999999"))

    assert calls == ["OMIM 999999"]
    assert result.model_used == "anthropic:claude-sonnet-5-5"


def test_wider_search_still_asks_the_models_for_a_name() -> None:
    calls: list[str] = []

    class _Identification:
        candidates: list[object] = []
        notes = ""
        judged = True
        judge_model = "anthropic:claude-sonnet-5-5"
        generator_model = ""

    async def lookup(query: str) -> object:
        calls.append(query)
        return _Identification()

    svc = WiderDiseaseSearchService(lookup=lookup, index=InMemoryDiseaseIndexRepo(seed=[_mas()]))
    asyncio.run(svc.search("pus3"))
    assert calls == ["pus3"]
