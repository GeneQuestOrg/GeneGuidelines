"""Parser tests for the Orphanet XML feeds.

Pin the parser against a small XML snippet (``fixtures/orphanet_*``)
that captures the production shape we depend on: name, synonyms,
OMIM cross-refs, ICD-10 codes, gene symbols. The fixture also covers
two edge cases — a disorder without external references (Tuberculosis)
and a long compound-name disorder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.disease_index.orphanet_loader import (
    build_aliases,
    parse_disorders,
    parse_gene_associations,
    to_index_entry,
)


_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_DISORDERS = _FIXTURES / "orphanet_disorders_sample.xml"
_GENES = _FIXTURES / "orphanet_genes_sample.xml"


@pytest.fixture
def disorders():
    return list(parse_disorders(_DISORDERS))


def test_parse_disorders_count(disorders):
    assert len(disorders) == 4


def test_parse_marfan_disorder(disorders):
    marfan = next(d for d in disorders if d.orpha_code == "558")
    assert marfan.name == "Marfan syndrome"
    assert "MFS" in marfan.synonyms
    assert marfan.omim_codes == ("154700",)
    assert marfan.icd10_codes == ("Q87.4",)
    assert marfan.disorder_type == "Disease"


def test_parse_pmm2_synonyms(disorders):
    pmm2 = next(d for d in disorders if d.orpha_code == "79318")
    assert pmm2.synonyms == (
        "CDG syndrome type Ia",
        "Phosphomannomutase 2 deficiency",
    )
    assert pmm2.omim_codes == ("212065",)


def test_parse_disorder_without_external_refs(disorders):
    tb = next(d for d in disorders if d.orpha_code == "3389")
    assert tb.name == "Tuberculosis"
    assert tb.synonyms == ()
    assert tb.omim_codes == ()
    assert tb.icd10_codes == ()


def test_parse_gene_associations():
    genes = parse_gene_associations(_GENES)
    assert genes["558"] == ("FBN1",)
    assert genes["79318"] == ("PMM2",)
    # Disorders not referenced in the gene XML must not appear.
    assert "3389" not in genes


def test_to_index_entry_marks_genetic(disorders):
    marfan = next(d for d in disorders if d.orpha_code == "558")
    entry = to_index_entry(
        marfan,
        gene_symbols=("FBN1",),
        refreshed_at="2026-05-24T00:00:00+00:00",
        source_version="orphanet-test",
    )
    assert entry.primary_id == "ORPHA:558"
    assert entry.source == "orphanet"
    assert entry.canonical_name == "Marfan syndrome"
    assert entry.canonical_name_norm == "marfan syndrome"
    assert entry.category == "genetic"
    assert entry.is_in_scope is True
    assert entry.gene_symbols == ("FBN1",)
    assert entry.omim_codes == ("154700",)
    assert entry.orpha_url == "https://www.orpha.net/en/disease/detail/558"
    assert entry.omim_url == "https://www.omim.org/entry/154700"
    assert entry.local_slug is None  # Orphanet ingest never sets local_slug


def test_to_index_entry_marks_tuberculosis_infectious(disorders):
    tb = next(d for d in disorders if d.orpha_code == "3389")
    entry = to_index_entry(
        tb,
        refreshed_at="2026-05-24T00:00:00+00:00",
        source_version="orphanet-test",
    )
    assert entry.category == "infectious"
    assert entry.is_in_scope is False


def test_build_aliases_kinds_and_dedup(disorders):
    marfan = next(d for d in disorders if d.orpha_code == "558")
    aliases = build_aliases(marfan, gene_symbols=("FBN1", "FBN1"))  # dup gene
    kinds = {alias.kind for alias in aliases}
    assert kinds == {"canonical", "synonym", "orpha", "omim", "icd10", "gene"}

    # Canonical alias carries the highest weight so the canonical name
    # outranks a same-string synonym hit at query time.
    canonical = next(a for a in aliases if a.kind == "canonical")
    synonym = next(a for a in aliases if a.kind == "synonym")
    assert canonical.weight > synonym.weight

    # Duplicate gene symbols collapse — the alias list does not blow up.
    gene_aliases = [a for a in aliases if a.kind == "gene"]
    assert len(gene_aliases) == 1


def test_build_aliases_normalises_polish_diacritics():
    """``alias_norm`` must be the same regardless of input diacritics."""
    from backend.disease_index.orphanet_loader import OrphanetDisorder

    disorder = OrphanetDisorder(
        orpha_code="558",
        name="Zespół Marfana",  # PL with diacritics
        synonyms=(),
    )
    aliases = build_aliases(disorder)
    canonical = next(a for a in aliases if a.kind == "canonical")
    assert canonical.alias == "Zespół Marfana"
    assert canonical.alias_norm == "zespol marfana"  # Polish ł folded to l
