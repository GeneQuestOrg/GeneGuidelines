from __future__ import annotations

import pytest

from backend.flows.doctor_finder.affiliation_parser import parse_affiliation, run
from backend.flows.doctor_finder.schemas import ParsedAffiliation


def test_italian_affiliation() -> None:
    result = parse_affiliation("Sapienza University of Rome, Rome, Italy")
    assert result.country_code == "IT"
    assert result.continent == "Europe"
    assert result.institution == "Sapienza University of Rome"


def test_usa_alias() -> None:
    result = parse_affiliation("UCSF, San Francisco, CA, USA")
    assert result.country_code == "US"
    assert result.continent == "North America"


def test_netherlands_alias() -> None:
    result = parse_affiliation("Department of Medicine, LUMC, Leiden, The Netherlands")
    assert result.country_code == "NL"
    assert result.continent == "Europe"


def test_australia() -> None:
    result = parse_affiliation("University Hospital, Brisbane, Australia")
    assert result.country_code == "AU"
    assert result.continent == "Oceania"


def test_uk_short_alias() -> None:
    result = parse_affiliation("UK")
    assert result.country_code == "GB"
    assert result.continent == "Europe"


def test_uk_dotted_alias() -> None:
    result = parse_affiliation("U.K.")
    assert result.country_code == "GB"
    assert result.continent == "Europe"


def test_united_kingdom_full() -> None:
    result = parse_affiliation("United Kingdom")
    assert result.country_code == "GB"
    assert result.continent == "Europe"


def test_empty_string() -> None:
    result = parse_affiliation("")
    assert result.raw == ""
    assert result.institution is None
    assert result.city is None
    assert result.country_name is None
    assert result.country_code is None
    assert result.continent is None


def test_two_token_affiliation_city_is_none() -> None:
    result = parse_affiliation("University Hospital, Germany")
    assert result.country_code == "DE"
    assert result.city is None
    assert result.institution == "University Hospital"


def test_unrecognized_affiliation() -> None:
    result = parse_affiliation("Some Random Institution XYZ123Blah")
    assert result.country_code is None
    assert result.continent is None


def test_country_second_from_last_token() -> None:
    """PubMed-style trailing city: country is not always the last comma segment."""
    result = parse_affiliation("National Institute of Cardiology, Warsaw, Poland")
    assert result.country_code == "PL"
    assert result.continent == "Europe"


def test_bangladesh_maps_asia() -> None:
    result = parse_affiliation("Dhaka Medical College, Dhaka, Bangladesh")
    assert result.country_code == "BD"
    assert result.continent == "Asia"


def test_us_state_abbrev_not_morocco_when_followed_by_country() -> None:
    result = parse_affiliation("Washington University, St. Louis, MO, United States")
    assert result.country_code == "US"
    assert result.continent == "North America"


def test_pubmed_trailing_period_after_country() -> None:
    """PubMed Medline often ends the country segment with a full stop before email."""
    raw = (
        "Department of Molecular Medicine, Sapienza University of Rome, "
        "Viale Regina Elena 324, Rome, 00161, Italy. mara.riminucci@uniroma1.it."
    )
    result = parse_affiliation(raw)
    assert result.country_code == "IT"
    assert result.continent == "Europe"


def test_pubmed_country_token_with_embedded_email_suffix() -> None:
    """Same pattern as Orphanet J Rare Dis 2025 review (PMID 40781626): ``USA. localpart@domain``."""
    raw = (
        "Division of Endocrinology and Metabolism, Department of Medicine, "
        "The Institute for Human Genetics; and the Eli and Edythe Broad Institute for Regeneration Medicine, "
        "University of California, San Francisco, CA, 94143, USA. edward.Hsiao@ucsf.edu."
    )
    result = parse_affiliation(raw)
    assert result.country_code == "US"
    assert result.continent == "North America"


def test_pubmed_country_token_email_without_space_before_at() -> None:
    raw = "Department of Molecular Medicine, Sapienza University of Rome, Rome, Italy.mara.riminucci@uniroma1.it"
    result = parse_affiliation(raw)
    assert result.country_code == "IT"


def test_run_enriches_authors() -> None:
    context = {
        "articles": [
            {
                "pmid": "12345",
                "authors": [
                    {
                        "last_name": "Rossi",
                        "affiliations_raw": ["Sapienza University of Rome, Rome, Italy"],
                    },
                    {
                        "last_name": "Smith",
                        "affiliations_raw": ["Some Unknown Place XYZ"],
                    },
                    {
                        "last_name": "NoAff",
                        "affiliations_raw": [],
                    },
                ],
            }
        ]
    }
    result = run(context)

    authors = result["articles"][0]["authors"]

    rossi = authors[0]
    assert rossi["parsed_affiliation"] is not None
    assert rossi["parsed_affiliation"]["country_code"] == "IT"
    assert rossi["parsed_affiliation"]["continent"] == "Europe"

    smith = authors[1]
    assert smith["parsed_affiliation"] is not None
    assert smith["parsed_affiliation"]["country_code"] is None

    no_aff = authors[2]
    assert no_aff["parsed_affiliation"] is None
