"""Clinician removal that sticks: the list holds hashes only, and it is applied when the directory is read and when a doctor-finder run is stored."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import backend.doctor_removals as removals
from backend import doctor_catalog, doctor_finder_store
from backend.content_models import PracticeResponse
from backend.doctor_catalog import _entry_to_public_doctor, slugify_doctor_name
from backend.routers.doctor_finder import _without_street_addresses


@pytest.fixture
def removal_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "doctor_removals.json"
    path.write_text(json.dumps({"entries": []}), encoding="utf-8")
    monkeypatch.setattr(removals, "REMOVALS_PATH", path)
    return path


def _author(name: str, orcid: str) -> dict:
    return {"display_name": name, "author_key": f"orcid:{orcid}", "affiliation": "Somewhere University, Poland"}


def test_the_real_list_is_valid_and_holds_no_plain_identifiers() -> None:
    data = json.loads(removals.REMOVALS_PATH.read_text(encoding="utf-8"))
    for entry in data["entries"]:
        assert set(entry) == {"sha256", "reason", "date"}
        assert len(entry["sha256"]) == 64
        assert entry["reason"] in removals.REASONS


def test_add_removal_stores_a_hash_not_the_slug_and_is_idempotent(removal_file: Path) -> None:
    first = removals.add_removal("orcid-0000-0002-1825-0097", "objection", today=date(2026, 11, 20))
    again = removals.add_removal("orcid-0000-0002-1825-0097", "objection", today=date(2026, 12, 1))
    text = removal_file.read_text(encoding="utf-8")
    assert "0000-0002-1825-0097" not in text
    assert first == again == {"sha256": removals.slug_hash("orcid-0000-0002-1825-0097"), "reason": "objection", "date": "2026-11-20"}
    assert len(json.loads(text)["entries"]) == 1
    with pytest.raises(ValueError):
        removals.add_removal("someone", "because")


def test_read_time_rows_are_dropped_by_slug(removal_file: Path) -> None:
    removals.add_removal("jane-doe", "erasure")
    rows = [{"slug": "jane-doe"}, {"slug": "john-roe"}]
    assert removals.without_removed(rows) == [{"slug": "john-roe"}]
    assert removals.is_removed("JANE-DOE ")


def test_every_per_disease_list_goes_through_the_filter(removal_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    removals.add_removal("jane-doe", "objection")
    monkeypatch.setattr(
        doctor_catalog,
        "_merged_doctors_for_catalog_slug_unfiltered",
        lambda *a, **k: ("doctor_finder", [{"slug": "jane-doe"}, {"slug": "john-roe"}]),
    )
    source, doctors = doctor_catalog._merged_doctors_for_catalog_slug("fd", {})
    assert source == "doctor_finder"
    assert [d["slug"] for d in doctors] == ["john-roe"]


def test_write_time_a_new_run_does_not_store_a_removed_author(removal_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    removed = _author("Jane Doe", "0000-0001-2345-6789")
    kept = _author("John Roe", "0000-0009-8765-4321")
    removals.add_removal(slugify_doctor_name(removed["display_name"], removed["author_key"]), "objection")

    executed: list[tuple] = []

    class _Cursor:
        def execute(self, sql, params=None):
            executed.append((sql, params))

    class _Conn:
        def cursor(self):
            return _Cursor()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(doctor_finder_store, "get_connection", lambda: _Conn())
    monkeypatch.setattr(doctor_catalog, "clear_finder_docs_index", lambda: None)
    doctor_finder_store.save_doctor_finder_run_result(
        "exec-1",
        disease_name="Fibrous dysplasia",
        catalog_slug=None,
        doctor_report={"top_authors": [removed, kept]},
        error=None,
        started_at="2026-11-20T10:00:00+00:00",
    )
    insert = next(params for sql, params in executed if params and "INSERT INTO doctor_finder_run_results" in sql)
    stored = json.loads(insert[3])
    assert [a["display_name"] for a in stored["top_authors"]] == ["John Roe"]


def test_strip_is_a_no_op_without_removals(removal_file: Path) -> None:
    report = {"top_authors": [_author("Jane Doe", "0000-0001-2345-6789")]}
    assert removals.strip_removed_authors(report) is report


def test_nppes_street_address_never_leaves_the_backend() -> None:
    entry = {
        "display_name": "Jane Doe",
        "author_key": "orcid:0000-0001-2345-6789",
        "affiliation": "Mercy Hospital, Boston, MA, USA",
        "country": "US",
        "resolved_practice": {"city": "Boston", "state": "MA", "country": "US", "address": "1 Main Street", "source": "nppes"},
    }
    public = _entry_to_public_doctor(entry, diseases=["fd"], source="doctor_finder")
    assert public["practices"][0]["address"] is None
    assert public["practices"][0]["city"] == "Boston"
    assert PracticeResponse(name="Mercy", city="Boston", address="1 Main Street", source="nppes").address is None
    assert PracticeResponse(name="Clinic", city="Olsztyn", address="ul. Żołnierska 18a", source="curated").address == "ul. Żołnierska 18a"
    run_report = {"top_authors": [{**entry}]}
    assert _without_street_addresses(run_report)["top_authors"][0]["resolved_practice"]["address"] is None
    assert entry["resolved_practice"]["address"] == "1 Main Street"  # the stored snapshot itself is not mutated
