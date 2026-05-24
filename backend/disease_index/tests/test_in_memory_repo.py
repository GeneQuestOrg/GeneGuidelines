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
    source: str = "manual",
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
        source=source,  # type: ignore[arg-type]
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


def test_curated_marfan_beats_orphanet_long_tail() -> None:
    """The hand-curated ``Marfan Syndrome`` entry must outrank the
    Orphanet long-tail (``Marfanoid syndrome``, ``Marfan syndrome type 1``,
    …) when the user types ``marfan``. Reproduces the production ranking
    regression observed 2026-05-24 where the manual entry sank to #8.
    """
    repo = InMemoryDiseaseIndexRepo(
        seed=[
            # Orphanet long-tail seeded first to make sure the manual
            # entry wins on score, not on insertion order.
            _entry(
                primary_id="ORPHA:2464",
                name="Marfanoid syndrome, De Silva type",
                source="orphanet",
            ),
            _entry(
                primary_id="ORPHA:2463",
                name="Marfanoid habitus-autosomal recessive intellectual disability syndrome",
                source="orphanet",
            ),
            _entry(
                primary_id="ORPHA:284993",
                name="Marfan syndrome and Marfan-related disorders",
                source="orphanet",
            ),
            _entry(
                primary_id="ORPHA:284973",
                name="Marfan syndrome type 2",
                source="orphanet",
            ),
            _entry(
                primary_id="ORPHA:284963",
                name="Marfan syndrome type 1",
                source="orphanet",
                genes=("FBN1",),
            ),
            _entry(
                primary_id="ORPHA:558",
                name="Marfan Syndrome",
                source="manual",
                omim="154700",
                orpha="558",
                genes=("FBN1",),
                local_slug="marfan-syndrome",
            ),
        ]
    )
    hits = repo.search("marfan", limit=10)
    assert hits, "expected at least one hit"
    top_entry = hits[0][0]
    assert top_entry.primary_id == "ORPHA:558", (
        f"Marfan Syndrome (manual) must rank first, got "
        f"{[(h[0].canonical_name, round(h[2], 2)) for h in hits[:5]]}"
    )


def test_curated_marfan_wins_when_user_types_gene_fbn1() -> None:
    """Typing the gene ``FBN1`` should surface the curated
    ``Marfan Syndrome`` ahead of the half-dozen other FBN1-associated
    Orphanet entries (``Isolated ectopia lentis``, ``Acromicric
    dysplasia``, …). Mirrors the prod bug where Marfan was at #12.
    """
    repo = InMemoryDiseaseIndexRepo(
        seed=[
            _entry(
                primary_id="ORPHA:1885",
                name="Isolated ectopia lentis",
                source="orphanet",
                genes=("FBN1",),
            ),
            _entry(
                primary_id="ORPHA:969",
                name="Acromicric dysplasia",
                source="orphanet",
                genes=("FBN1",),
            ),
            _entry(
                primary_id="ORPHA:2462",
                name="Shprintzen-Goldberg syndrome",
                source="orphanet",
                genes=("FBN1",),
            ),
            _entry(
                primary_id="ORPHA:558",
                name="Marfan Syndrome",
                source="manual",
                genes=("FBN1",),
                local_slug="marfan-syndrome",
            ),
        ]
    )
    hits = repo.search("FBN1", limit=10)
    top_entry, top_alias, _ = hits[0]
    assert top_entry.primary_id == "ORPHA:558"
    assert top_alias.kind == "gene"


def test_curated_fd_synonym_beats_orphanet_substring_matches() -> None:
    """Don't regress the working FD case: ``fd`` synonym exact-match
    must still beat ``FDFM`` / ``FDLAB`` prefix matches.
    """
    repo = InMemoryDiseaseIndexRepo(
        seed=[
            _entry(
                primary_id="ORPHA:249",
                name="Fibrous Dysplasia",
                source="manual",
                synonyms=("FD",),
                local_slug="fd",
            ),
            _entry(
                primary_id="ORPHA:329336",
                name="Familial dyskinesia and facial myokymia",
                source="orphanet",
                synonyms=("FDFM",),
            ),
            _entry(
                primary_id="ORPHA:217260",
                name="Facial dysmorphism-lens dislocation syndrome",
                source="orphanet",
                synonyms=("FDLAB syndrome",),
            ),
        ]
    )
    hits = repo.search("fd", limit=5)
    assert hits[0][0].primary_id == "ORPHA:249"


def test_word_boundary_prefix_beats_in_word_prefix() -> None:
    """``"Marfan syndrome type 1"`` (word-boundary prefix of ``marfan``)
    must rank above ``"Marfanoid syndrome"`` (in-word prefix) when both
    come from the same source.
    """
    repo = InMemoryDiseaseIndexRepo(
        seed=[
            _entry(
                primary_id="ORPHA:2464",
                name="Marfanoid syndrome, De Silva type",
                source="orphanet",
            ),
            _entry(
                primary_id="ORPHA:284963",
                name="Marfan syndrome type 1",
                source="orphanet",
            ),
        ]
    )
    hits = repo.search("marfan", limit=5)
    assert hits[0][0].primary_id == "ORPHA:284963"


def test_upsert_round_trip() -> None:
    repo = InMemoryDiseaseIndexRepo()
    repo.upsert(_entry(primary_id="ORPHA:1", name="Foo"))
    again = _entry(primary_id="ORPHA:1", name="Foo (renamed)")
    repo.upsert(again)
    assert repo.count() == 1
    fetched = repo.get_by_primary_id("ORPHA:1")
    assert fetched is not None and fetched.canonical_name == "Foo (renamed)"
