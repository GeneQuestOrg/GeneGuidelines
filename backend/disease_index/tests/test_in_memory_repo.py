"""Unit tests for the in-memory disease-index repository.

The in-memory repo is the production fall-back for offline / dev mode
*and* the implementation under test for the search algorithm. The
SQLAlchemy repo defers to the same scoring function, so getting these
tests green is a strong proxy for the algorithm being correct.
"""

from __future__ import annotations

from backend.disease_index.models import (
    DiseaseAlias,
    DiseaseIndexEntry,
)
from backend.disease_index.repository import (
    InMemoryDiseaseIndexRepo,
    normalize_term,
)


def _entry(
    *,
    primary_id: str,
    name: str,
    omim: str = "",
    orpha: str = "",
    genes: tuple[str, ...] = (),
    synonyms: tuple[str, ...] = (),
    local_slug: str | None = None,
) -> DiseaseIndexEntry:
    aliases = [
        DiseaseAlias(
            alias=name,
            alias_norm=normalize_term(name),
            kind="canonical",
            weight=1.6,
        )
    ]
    for synonym in synonyms:
        aliases.append(
            DiseaseAlias(
                alias=synonym,
                alias_norm=normalize_term(synonym),
                kind="synonym",
                weight=1.3,
            )
        )
    if omim:
        aliases.append(
            DiseaseAlias(
                alias=omim,
                alias_norm=normalize_term(omim),
                kind="omim",
                weight=0.9,
            )
        )
    if orpha:
        aliases.append(
            DiseaseAlias(
                alias=orpha,
                alias_norm=normalize_term(orpha),
                kind="orpha",
                weight=1.0,
            )
        )
    for gene in genes:
        aliases.append(
            DiseaseAlias(
                alias=gene,
                alias_norm=normalize_term(gene),
                kind="gene",
                weight=1.2,
            )
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
        omim_codes=(omim,) if omim else (),
        gene_symbols=genes,
        local_slug=local_slug,
        refreshed_at="2026-01-01T00:00:00Z",
        aliases=tuple(aliases),
    )


def _repo() -> InMemoryDiseaseIndexRepo:
    return InMemoryDiseaseIndexRepo(
        seed=[
            _entry(
                primary_id="ORPHA:558",
                name="Marfan Syndrome",
                omim="154700",
                orpha="558",
                genes=("FBN1",),
                synonyms=("Zespół Marfana",),
            ),
            _entry(
                primary_id="ORPHA:249",
                name="Fibrous Dysplasia",
                omim="174800",
                orpha="249",
                genes=("GNAS",),
                synonyms=("FD", "Dysplazja włóknista"),
                local_slug="fd",
            ),
            _entry(
                primary_id="ORPHA:110",
                name="Bardet-Biedl Syndrome",
                omim="209900",
                orpha="110",
                genes=("BBS1", "BBS10"),
                synonyms=("BBS",),
            ),
        ]
    )


def test_search_by_canonical_name() -> None:
    hits = _repo().search("marfan", limit=5)
    assert hits, "expected at least one hit"
    entry, alias, score = hits[0]
    assert entry.primary_id == "ORPHA:558"
    assert alias.kind == "canonical"
    assert score > 0


def test_search_by_gene_symbol_exact_match() -> None:
    hits = _repo().search("FBN1", limit=5)
    assert hits[0][0].primary_id == "ORPHA:558"
    # The gene-exact bonus pushes the gene-matched alias above the
    # canonical-name-prefix match for the same disease.
    assert hits[0][1].kind == "gene"


def test_search_by_omim_number() -> None:
    hits = _repo().search("154700", limit=5)
    assert hits[0][0].primary_id == "ORPHA:558"
    assert hits[0][1].kind == "omim"


def test_search_by_polish_synonym_with_diacritics() -> None:
    hits = _repo().search("zespół marfana", limit=5)
    assert hits and hits[0][0].primary_id == "ORPHA:558"


def test_search_token_and_filter_drops_non_matches() -> None:
    """Every token must appear in some alias for the disease to match."""
    repo = _repo()
    hits_one = repo.search("fibrous", limit=5)
    hits_two = repo.search("fibrous zebra", limit=5)
    assert any(entry.primary_id == "ORPHA:249" for entry, _, _ in hits_one)
    assert all(entry.primary_id != "ORPHA:249" for entry, _, _ in hits_two)


def test_search_unknown_query_returns_empty() -> None:
    assert _repo().search("xyzzyplugh", limit=5) == []


def test_search_empty_query_returns_empty() -> None:
    assert _repo().search("   ", limit=5) == []


def test_canonical_match_outranks_synonym_match() -> None:
    """When two diseases tie on tokens, the canonical-name match wins.

    Searching ``BBS`` matches both ``Bardet-Biedl Syndrome`` (synonym
    ``BBS``) and ``BBS1`` / ``BBS10`` gene aliases on the same row. The
    repository must return Bardet-Biedl as the top hit.
    """
    hits = _repo().search("BBS", limit=5)
    assert hits and hits[0][0].primary_id == "ORPHA:110"


def test_upsert_round_trip() -> None:
    repo = InMemoryDiseaseIndexRepo()
    repo.upsert(_entry(primary_id="ORPHA:1", name="Foo"))
    again = _entry(primary_id="ORPHA:1", name="Foo (renamed)")
    repo.upsert(again)
    assert repo.count() == 1
    fetched = repo.get_by_primary_id("ORPHA:1")
    assert fetched is not None and fetched.canonical_name == "Foo (renamed)"
