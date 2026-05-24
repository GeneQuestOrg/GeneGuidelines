"""End-to-end test for the Orphanet bulk-import path against the local
Postgres engine. The fixture XML is tiny (4 disorders, 2 genes) so the
test runs in <0.5 s; it covers the parts the unit tests cannot reach:

- ``bulk_upsert_orphanet`` actually writes rows to Postgres;
- the ``preserve manual`` rule does *not* erase a hand-curated row;
- ``bulk_replace_aliases`` syncs alias kinds for inserted rows;
- the ``DiseaseSuggestionService`` finds Orphanet-imported diseases
  via name, gene, OMIM, ICD-10 and Orphanet code.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import delete, insert

from backend.content_db import ensure_content_schema
from backend.content.repository import InMemoryDiseaseRepo
from backend.disease_index.repository import (
    SqlaDiseaseIndexRepo,
    ensure_disease_index_schema,
)
from backend.disease_index.seeds import import_orphanet_disorders
from backend.disease_index.service import DiseaseSuggestionService
from backend.shared.persistence.engine import get_engine
from backend.shared.persistence.schema import (
    disease_index as disease_index_table,
    disease_index_aliases as aliases_table,
)


_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_DISORDERS = _FIXTURES / "orphanet_disorders_sample.xml"
_GENES = _FIXTURES / "orphanet_genes_sample.xml"


@pytest.fixture
def fresh_index():
    """Wipe ``disease_index`` + aliases so each test starts from a clean slate."""
    ensure_content_schema()
    ensure_disease_index_schema()
    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(delete(aliases_table))
            conn.execute(delete(disease_index_table))
    yield
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(delete(aliases_table))
            conn.execute(delete(disease_index_table))


def test_bulk_import_writes_rows_to_postgres(fresh_index):
    result = import_orphanet_disorders(
        disorders_xml=_DISORDERS,
        genes_xml=_GENES,
        repo=SqlaDiseaseIndexRepo(),
    )
    assert result.parsed == 4
    assert result.inserted == 4
    assert result.updated == 0
    assert result.skipped_manual == 0
    # 1 canonical + N synonyms + omim/orpha/icd10/gene per disorder.
    assert result.aliases_written > 4


def test_search_finds_imported_marfan(fresh_index):
    import_orphanet_disorders(
        disorders_xml=_DISORDERS,
        genes_xml=_GENES,
        repo=SqlaDiseaseIndexRepo(),
    )
    service = DiseaseSuggestionService(
        repo=SqlaDiseaseIndexRepo(),
        disease_repo=InMemoryDiseaseRepo(),
    )

    by_name = service.suggest("marfan")
    assert by_name and by_name[0].entry.primary_id == "ORPHA:558"

    by_gene = service.suggest("FBN1")
    assert by_gene and by_gene[0].entry.primary_id == "ORPHA:558"
    assert by_gene[0].matched_alias.kind == "gene"

    by_omim = service.suggest("154700")
    assert by_omim and by_omim[0].entry.primary_id == "ORPHA:558"
    assert by_omim[0].matched_alias.kind == "omim"

    by_icd = service.suggest("Q87.4")
    assert by_icd and by_icd[0].entry.primary_id == "ORPHA:558"
    assert by_icd[0].matched_alias.kind == "icd10"


def test_pmm2_cdg_searchable_after_import(fresh_index):
    import_orphanet_disorders(
        disorders_xml=_DISORDERS,
        genes_xml=_GENES,
        repo=SqlaDiseaseIndexRepo(),
    )
    service = DiseaseSuggestionService(
        repo=SqlaDiseaseIndexRepo(),
        disease_repo=InMemoryDiseaseRepo(),
    )
    hits = service.suggest("PMM2-CDG")
    assert hits and hits[0].entry.primary_id == "ORPHA:79318"


def test_tuberculosis_marked_out_of_scope(fresh_index):
    import_orphanet_disorders(
        disorders_xml=_DISORDERS,
        repo=SqlaDiseaseIndexRepo(),
    )
    service = DiseaseSuggestionService(
        repo=SqlaDiseaseIndexRepo(),
        disease_repo=InMemoryDiseaseRepo(),
    )
    hits = service.suggest("tuberculosis")
    assert hits, "Tuberculosis should still be in the index even if out of scope"
    entry = hits[0].entry
    assert entry.category == "infectious"
    assert entry.is_in_scope is False


def test_manual_rows_are_preserved_on_reimport(fresh_index):
    """A hand-curated entry must not be overwritten by the Orphanet ingest."""
    repo = SqlaDiseaseIndexRepo()
    engine = get_engine()
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                insert(disease_index_table).values(
                    primary_id="ORPHA:558",
                    source="manual",
                    canonical_name="Marfan Syndrome — manually curated",
                    canonical_name_norm="marfan syndrome manually curated",
                    category="genetic",
                    is_in_scope=True,
                    omim_codes_json=json.dumps(["154700"]),
                    gene_symbols_json=json.dumps(["FBN1"]),
                    local_slug="marfan-syndrome",
                    refreshed_at=datetime.now(UTC).isoformat(),
                )
            )

    result = import_orphanet_disorders(
        disorders_xml=_DISORDERS,
        genes_xml=_GENES,
        repo=repo,
    )
    assert result.skipped_manual == 1, "Marfan row was source='manual'; must be skipped"
    # The other three disorders still flow through.
    assert result.inserted == 3

    # Row content must be the curated string, not Orphanet's name.
    fetched = repo.get_by_primary_id("ORPHA:558")
    assert fetched is not None
    assert fetched.canonical_name == "Marfan Syndrome — manually curated"
    assert fetched.source == "manual"
    assert fetched.local_slug == "marfan-syndrome"


def test_idempotent_reimport(fresh_index):
    """Running the loader twice does not duplicate aliases or change counts."""
    first = import_orphanet_disorders(
        disorders_xml=_DISORDERS,
        genes_xml=_GENES,
        repo=SqlaDiseaseIndexRepo(),
    )
    assert first.inserted == 4

    second = import_orphanet_disorders(
        disorders_xml=_DISORDERS,
        genes_xml=_GENES,
        repo=SqlaDiseaseIndexRepo(),
    )
    assert second.inserted == 0
    assert second.updated == 4
    assert second.skipped_manual == 0
