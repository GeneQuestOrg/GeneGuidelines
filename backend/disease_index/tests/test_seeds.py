"""Seeder integrates the alias builder, the in-memory repo and the
production seed list. A green run here means a local dev environment
ships with a working autocomplete the moment ``init_db`` finishes —
without needing Postgres or Orphanet.
"""

from __future__ import annotations

from backend.disease_index.repository import InMemoryDiseaseIndexRepo
from backend.disease_index.seeds import (
    _SEED_RECORDS,
    seed_disease_index_if_empty,
)


# Production differs from draft6 by one entry: Marfan was promoted from
# "indexed-only" to "covered" because the production database already has
# a marfan-syndrome bootstrap (see plan-postgres-migration §Wykonanie).
EXPECTED_SEED_COUNT = 31


def test_seeder_populates_in_memory_repo() -> None:
    repo = InMemoryDiseaseIndexRepo()
    written = seed_disease_index_if_empty(repo)
    assert written == len(_SEED_RECORDS) == EXPECTED_SEED_COUNT
    assert repo.count() == EXPECTED_SEED_COUNT


def test_seeder_is_idempotent() -> None:
    repo = InMemoryDiseaseIndexRepo()
    first = seed_disease_index_if_empty(repo)
    second = seed_disease_index_if_empty(repo)
    # Both calls report the count because the seeder unconditionally
    # re-asserts the manual records — the contract is that the table
    # always ends up with exactly the 31 hand-curated rows, regardless
    # of whether a prior Orphanet ingest had stamped over them.
    assert first == EXPECTED_SEED_COUNT
    assert second == EXPECTED_SEED_COUNT
    assert repo.count() == EXPECTED_SEED_COUNT


def test_seed_marks_covered_diseases_with_local_slug() -> None:
    repo = InMemoryDiseaseIndexRepo()
    seed_disease_index_if_empty(repo)
    fd = repo.get_by_primary_id("ORPHA:249")
    marfan = repo.get_by_primary_id("ORPHA:558")
    bbs = repo.get_by_primary_id("ORPHA:110")
    assert fd is not None and fd.local_slug == "fd"
    assert marfan is not None and marfan.local_slug == "marfan-syndrome"
    assert bbs is not None and bbs.local_slug is None  # only seeded — bootstrap pending


def test_seed_round_trips_alias_search() -> None:
    repo = InMemoryDiseaseIndexRepo()
    seed_disease_index_if_empty(repo)

    # FD by canonical English name
    hits = repo.search("Fibrous Dysplasia", limit=5)
    assert hits and hits[0][0].primary_id == "ORPHA:249"

    # FD by Polish synonym (with diacritics)
    hits = repo.search("Dysplazja włóknista", limit=5)
    assert hits and hits[0][0].primary_id == "ORPHA:249"

    # FD by gene
    hits = repo.search("GNAS", limit=5)
    assert any(h[0].primary_id == "ORPHA:249" for h in hits)

    # OMIM 209900 → Bardet-Biedl
    hits = repo.search("209900", limit=5)
    assert hits and hits[0][0].primary_id == "ORPHA:110"

    # ORPHA exact match
    hits = repo.search("558", limit=5)
    assert any(h[0].primary_id == "ORPHA:558" for h in hits)


def test_every_seed_record_has_canonical_alias() -> None:
    repo = InMemoryDiseaseIndexRepo()
    seed_disease_index_if_empty(repo)
    for record in _SEED_RECORDS:
        entry = repo.get_by_primary_id(f"ORPHA:{record.orpha}")
        assert entry is not None, f"missing entry for {record.name}"
        kinds = {a.kind for a in entry.aliases}
        assert "canonical" in kinds
        assert entry.category == "genetic"
        assert entry.is_in_scope is True
