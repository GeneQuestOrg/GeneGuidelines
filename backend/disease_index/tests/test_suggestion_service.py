"""Service-level tests for :class:`DiseaseSuggestionService`.

We use the in-memory repos for both the index and the disease catalogue
so the assertions cover the cross-reference logic that decides whether a
suggestion gets the "✓ wytyczne" or the "research" badge.
"""

from __future__ import annotations

from backend.content.models import Disease
from backend.content.repository import InMemoryDiseaseRepo
from backend.disease_index.models import (
    DiseaseAlias,
    DiseaseIndexEntry,
)
from backend.disease_index.repository import (
    InMemoryDiseaseIndexRepo,
    normalize_term,
)
from backend.disease_index.service import DiseaseSuggestionService


def _entry(
    *,
    primary_id: str,
    name: str,
    local_slug: str | None,
) -> DiseaseIndexEntry:
    aliases = (
        DiseaseAlias(
            alias=name,
            alias_norm=normalize_term(name),
            kind="canonical",
            weight=1.6,
        ),
    )
    return DiseaseIndexEntry(
        primary_id=primary_id,
        source="manual",
        canonical_name=name,
        canonical_name_norm=normalize_term(name),
        category="genetic",
        is_in_scope=True,
        inheritance=None,
        summary="",
        local_slug=local_slug,
        refreshed_at="2026-01-01T00:00:00Z",
        aliases=aliases,
    )


def _disease(slug: str) -> Disease:
    return Disease(
        slug=slug,
        name=slug.upper(),
        name_short=slug.upper(),
        omim="0",
        gene="",
        inheritance="",
        summary="",
        prevalence_text="",
        status="consensus",
        coverage="full",
        accent="teal",
    )


def test_suggestion_marks_known_local_records() -> None:
    index = InMemoryDiseaseIndexRepo(
        seed=[
            _entry(primary_id="ORPHA:249", name="Fibrous Dysplasia", local_slug="fd"),
            _entry(primary_id="ORPHA:558", name="Marfan Syndrome", local_slug=None),
        ]
    )
    diseases = InMemoryDiseaseRepo(seed=[_disease("fd")])
    svc = DiseaseSuggestionService(repo=index, disease_repo=diseases)

    fd_hit = next(s for s in svc.suggest("fibrous") if s.entry.primary_id == "ORPHA:249")
    marfan_hit = next(s for s in svc.suggest("marfan") if s.entry.primary_id == "ORPHA:558")

    assert fd_hit.has_local_record is True
    assert marfan_hit.has_local_record is False


def test_suggestion_falls_back_when_disease_repo_fails() -> None:
    """A degraded disease catalogue must not break the autocomplete."""

    class _BrokenRepo:
        def list_all(self) -> list[Disease]:
            raise RuntimeError("simulated outage")

        def get(self, slug: str) -> Disease | None:
            return None

    index = InMemoryDiseaseIndexRepo(
        seed=[_entry(primary_id="ORPHA:249", name="Fibrous Dysplasia", local_slug="fd")]
    )
    svc = DiseaseSuggestionService(repo=index, disease_repo=_BrokenRepo())  # type: ignore[arg-type]

    suggestions = svc.suggest("fibrous")
    assert suggestions and suggestions[0].has_local_record is False


def test_empty_query_returns_empty() -> None:
    svc = DiseaseSuggestionService(
        repo=InMemoryDiseaseIndexRepo(),
        disease_repo=InMemoryDiseaseRepo(),
    )
    assert svc.suggest("") == []
    assert svc.suggest("   ") == []
