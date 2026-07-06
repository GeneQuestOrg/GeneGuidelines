"""Phase 1 specialty enrichment: NUCC taxonomy, NPPES disambiguation, enrich stage."""
from __future__ import annotations

import asyncio

import pytest

from backend.flows.doctor_finder import nppes, specialty_enrich, specialty_taxonomy


# --- NUCC taxonomy (loads the real committed data asset) -------------------------------------

def test_taxonomy_loads_and_maps_known_codes() -> None:
    assert specialty_taxonomy.is_loaded()
    assert specialty_taxonomy.label_for_code("207X00000X") == "Orthopaedic Surgery"
    assert specialty_taxonomy.label_for_code("2080P0205X") == "Pediatric Endocrinology"


def test_taxonomy_normalizes_free_string_to_canonical_code() -> None:
    assert specialty_taxonomy.normalize_specialty("Orthopaedic Surgery") == "207X00000X"
    # Punctuation/case-insensitive.
    assert specialty_taxonomy.normalize_specialty("oral & maxillofacial surgery") == "204E00000X"
    assert specialty_taxonomy.normalize_specialty("not a real specialty zzz") is None


# --- NPPES disambiguation (the make-or-break identity logic) ---------------------------------

def _result(first, last, code, grouping, *, city="", state="", etype="NPI-1", primary=True):
    return {
        "enumeration_type": etype,
        "number": "1234567890",
        "basic": {"first_name": first, "last_name": last},
        "taxonomies": [{"code": code, "desc": "x", "grouping": grouping, "primary": primary}],
        "addresses": [
            {"address_purpose": "LOCATION", "city": city, "state": state, "address_1": "1 St"}
        ],
    }


def test_nppes_pick_refuses_when_multiple_physicians_match() -> None:
    # Two physician-ish individuals with the same initial -> ambiguous -> no guess.
    results = [
        _result("Alison", "Boyce", "2080P0205X", "Allopathic & Osteopathic Physicians"),
        _result("Adam", "Boyce", "207X00000X", "Allopathic & Osteopathic Physicians"),
    ]
    # first_initial "a" matches both -> None
    assert nppes._pick(results, first_initial="a", have_state=False) is None


def test_nppes_pick_ignores_non_physicians_and_matches_the_doctor() -> None:
    results = [
        _result("Alison", "Boyce", "363L00000X", "Physician Assistants & Advanced Practice Nursing Providers"),
        _result("Alison", "Boyce", "225700000X", "Respiratory, Developmental, Rehabilitative and Restorative Service Providers"),
        _result("Alison", "Boyce", "2080P0205X", "Allopathic & Osteopathic Physicians", city="Washington", state="DC"),
    ]
    match = nppes._pick(results, first_initial="a", have_state=True)
    assert match is not None
    assert match.taxonomy_code == "2080P0205X"
    assert match.confidence == "high"  # state was used
    assert match.city == "Washington" and match.state == "DC"


def test_nppes_pick_drops_org_records() -> None:
    results = [
        {**_result("", "Boyce Clinic", "2080P0205X", "Allopathic & Osteopathic Physicians"),
         "enumeration_type": "NPI-2"},
    ]
    assert nppes._pick(results, first_initial="", have_state=False) is None


# --- specialty_enrich stage (NPPES mocked; no network) --------------------------------------

def test_specialty_enrich_attaches_us_specialty_and_practice(monkeypatch) -> None:
    async def fake_lookup(*, last_name, first_name="", state="", client=None):
        if last_name == "Boyce":
            return nppes.NppesMatch(
                npi="1", first_name="Alison", last_name="Boyce",
                taxonomy_code="2080P0205X", taxonomy_desc="Pediatric Endocrinology",
                city="Washington", state="DC", confidence="high",
            )
        return None

    monkeypatch.setattr(nppes, "lookup_us_specialty", fake_lookup)

    context = {
        "aggregated_authors": [
            {"last_name": "Boyce", "fore_name": "Alison", "country_primary": "US",
             "paper_count": 30, "institution_primary": "NIH, Bethesda, MD 20892"},
            {"last_name": "Nowak", "fore_name": "Jan", "country_primary": "PL", "paper_count": 5},
        ]
    }
    out = asyncio.run(specialty_enrich.run_async(context))
    authors = {a["last_name"]: a for a in out["aggregated_authors"]}

    boyce = authors["Boyce"]
    assert boyce["clinical_specialties"][0]["canonicalCode"] == "2080P0205X"
    assert boyce["clinical_specialties"][0]["labelEn"] == "Pediatric Endocrinology"
    assert boyce["clinical_specialties"][0]["source"] == "nppes"
    assert boyce["reachability"] == "sees_patients"
    assert boyce["resolved_practice"]["city"] == "Washington"
    assert boyce["resolved_practice"]["country"] == "US"

    # Non-US author is untouched (Phase 1 is US-only).
    assert "clinical_specialties" not in authors["Nowak"]


def test_specialty_enrich_noop_when_no_us_authors(monkeypatch) -> None:
    called = {"n": 0}

    async def fake_lookup(**kwargs):
        called["n"] += 1
        return None

    monkeypatch.setattr(nppes, "lookup_us_specialty", fake_lookup)
    context = {"aggregated_authors": [{"last_name": "Nowak", "country_primary": "PL"}]}
    out = asyncio.run(specialty_enrich.run_async(context))
    assert out["aggregated_authors"][0].get("clinical_specialties") is None
    assert called["n"] == 0


def test_us_state_extracted_from_affiliation() -> None:
    author = {"institution_primary": "Metabolic Bone Disorders Unit, Bethesda, MD 20892"}
    assert specialty_enrich._us_state_from_author(author) == "MD"
    author2 = {"papers": [{"parsed_affiliation": {"raw": "Dept of Surgery, Ann Arbor, MI, USA"}}]}
    assert specialty_enrich._us_state_from_author(author2) == "MI"
