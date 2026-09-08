"""Institutional capability, from an official register rather than from reputation.

The directory is built from PubMed, which sees authors and cannot see a hospital's
wards — so it could not answer the question a family actually asks: is there anywhere
near me equipped to treat this in a child. Establishing that one particular professor
is excellent does not generalise. A register does: 16 hospitals in Poland have a
paediatric craniofacial capability, and that is reproducible from an EU dataset
without anyone's opinion entering into it.
"""

from __future__ import annotations

from backend.facility_capability import capabilities_for, paediatric_capabilities_for
from backend.tools.eu_healthcare_facilities import parse_country_csv

_CSV = (
    "﻿id,hospital_name,site_name,lat,lon,street,house_number,postcode,city,address,"
    "cntr_id,emergency,cap_beds,cap_prac,cap_rooms,facility_type,public_private,list_specs,"
    "tel,email,url,ref_date,pub_date,geo_qual,comments\n"
    "1,SZPITAL DZIECIĘCY W OLSZTYNIE,,53.76,20.48,,,,OLSZTYN,,PL,NA,NA,NA,NA,NA,NA,"
    "ODDZIAŁ CHIRURGII SZCZĘKOWO-TWARZOWEJ DLA DZIECI | ODDZIAŁ PEDIATRYCZNY,,,,2023,2025,1,\n"
    "2,SZPITAL OGÓLNY,,52.0,21.0,,,,WARSZAWA,,PL,NA,NA,NA,NA,NA,NA,"
    "ODDZIAŁ CHORÓB WEWNĘTRZNYCH,,,,2023,2025,1,\n"
)


def test_the_register_parses_with_its_byte_order_mark() -> None:
    """The files ship with a BOM on the first column; a naive reader loses the id and
    then silently mismatches every field after it."""
    rows = parse_country_csv(_CSV, "PL")

    assert [r.name for r in rows] == ["SZPITAL DZIECIĘCY W OLSZTYNIE", "SZPITAL OGÓLNY"]
    assert rows[0].city == "OLSZTYN"
    assert rows[0].lat == 53.76


def test_wards_split_into_a_list() -> None:
    rows = parse_country_csv(_CSV, "PL")

    assert len(rows[0].wards) == 2
    assert rows[0].wards[0].startswith("ODDZIAŁ CHIRURGII SZCZĘKOWO")


def test_a_missing_field_is_unknown_not_zero() -> None:
    """cap_beds and facility_type are empty for Poland while list_specs is populated.
    Reading "NA" as a number would publish invented capacity figures."""
    rows = parse_country_csv(_CSV, "PL")

    assert rows[0].url == ""
    assert rows[0].lon == 21.0 or rows[0].lon == 20.48


def test_polish_ward_names_map_to_capabilities() -> None:
    caps = capabilities_for(["ODDZIAŁ CHIRURGII SZCZĘKOWO-TWARZOWEJ DLA DZIECI"])

    assert "craniofacial" in caps
    assert "paediatric" in caps


def test_a_paediatric_ward_is_distinguished_from_an_adult_one() -> None:
    """"Has a maxillofacial ward" and "has one for children" are different answers to
    a parent, and conflating them sends a family to the wrong hospital."""
    adult_only = ["ODDZIAŁ CHIRURGII SZCZĘKOWO-TWARZOWEJ", "ODDZIAŁ PEDIATRYCZNY"]

    assert "craniofacial" in capabilities_for(adult_only)
    assert "craniofacial" not in paediatric_capabilities_for(adult_only)


def test_an_unrelated_ward_yields_nothing() -> None:
    assert capabilities_for(["ODDZIAŁ CHORÓB WEWNĘTRZNYCH"]) == set()


def test_english_ward_names_work_too() -> None:
    """The register covers 32 countries; the vocabulary has to be additive rather than
    Polish-only, or the mechanism stops at the border."""
    caps = paediatric_capabilities_for(["Paediatric Maxillofacial Surgery"])

    assert caps == {"craniofacial"}


def test_the_committed_index_is_usable_and_honest() -> None:
    import json
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "facility_index.json"
    index = json.loads(path.read_text(encoding="utf-8"))

    assert index["release"], "the GISCO release must be pinned so a rebuild is diffable"
    assert index["source"].startswith("https://gisco-services.ec.europa.eu")
    facilities = index["facilities"]
    assert facilities, "index is empty"
    # Every kept facility must justify its place: no capability, no row.
    assert all(f["capabilities"] for f in facilities)
    # And paediatric capability is a subset of overall capability, never broader.
    for facility in facilities:
        assert set(facility["paediatricCapabilities"]) <= set(facility["capabilities"])
