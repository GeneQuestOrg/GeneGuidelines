"""Joining a doctor to a registered hospital must be strict.

An unmatched doctor loses a badge. A mismatched one gets a claim about a building
they have never worked in — and that claim is what a family would travel on.
"""

from __future__ import annotations

import pytest

from backend.facility_lookup import capability_for


@pytest.fixture(autouse=True)
def _index(monkeypatch: pytest.MonkeyPatch):
    from backend import facility_lookup

    original = facility_lookup._index
    original.cache_clear()
    monkeypatch.setattr(
        facility_lookup,
        "_index",
        lambda: {
            "source": "https://gisco-services.ec.europa.eu/pub/healthcare/",
            "release": "2023_v2025_11",
            "facilities": [
                {
                    "name": "WOJEWÓDZKI SPECJALISTYCZNY SZPITAL DZIECIĘCY IM. PROF. DR STANISŁAWA POPOWSKIEGO",
                    "city": "OLSZTYN",
                    "country": "PL",
                    "capabilities": ["craniofacial", "paediatric", "skeletal"],
                    "paediatricCapabilities": ["craniofacial", "skeletal"],
                },
                {
                    "name": "SZPITAL DZIECIĘCY W KRAKOWIE",
                    "city": "KRAKÓW",
                    "country": "PL",
                    "capabilities": ["paediatric"],
                    "paediatricCapabilities": [],
                },
            ],
        },
    )
    yield
    original.cache_clear()


def test_an_abbreviated_name_still_matches_the_official_one() -> None:
    """Our records say "WSSD Olsztyn"; the register says the full official name. An
    exact match would find nothing at all."""
    found = capability_for(
        {
            "institution": "WSSD Olsztyn · Dowgierd Clinic",
            "city": "Olsztyn",
            "country": "PL",
            "practices": [{"name": "Wojewódzki Specjalistyczny Szpital Dziecięcy w Olsztynie"}],
        }
    )

    assert found is not None
    assert found.paediatric_capabilities == ("craniofacial", "skeletal")


def test_a_doctor_never_inherits_another_city_s_hospital() -> None:
    """Hospital naming repeats nationwide — "szpital dziecięcy" names half the
    country — so the Olsztyn capabilities must not follow the name to Kraków."""
    found = capability_for(
        {"institution": "Wojewódzki Specjalistyczny Szpital Dziecięcy", "city": "Kraków", "country": "PL"}
    )

    assert found is None or found.city == "KRAKÓW"
    assert found is None or "craniofacial" not in found.paediatric_capabilities


def test_a_tie_between_two_hospitals_needs_geography_not_a_guess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two children's hospitals in one city share the only word our record has. Names
    cannot separate them; without coordinates the honest answer is no answer."""
    from backend import facility_lookup

    twins = {
        "source": "https://gisco-services.ec.europa.eu/pub/healthcare/",
        "release": "2023_v2025_11",
        "facilities": [
            {"name": "SZPITAL DZIECIĘCY PÓŁNOC", "city": "OLSZTYN", "country": "PL",
             "lat": 53.90, "lon": 20.48, "capabilities": ["paediatric"], "paediatricCapabilities": []},
            {"name": "SZPITAL DZIECIĘCY POŁUDNIE", "city": "OLSZTYN", "country": "PL",
             "lat": 53.70, "lon": 20.48, "capabilities": ["craniofacial", "paediatric"],
             "paediatricCapabilities": ["craniofacial"]},
        ],
    }
    monkeypatch.setattr(facility_lookup, "_index", lambda: twins)

    blind = {"institution": "Szpital Dziecięcy", "city": "Olsztyn", "country": "PL"}
    assert capability_for(blind) is None

    located = {**blind, "lat": 53.71, "lng": 20.48}
    found = capability_for(located)
    assert found is not None and found.name.endswith("POŁUDNIE")


def test_generic_words_alone_are_not_a_match() -> None:
    """"Szpital", "centrum", "kliniczny" appear in most Polish hospital names; matching
    on them would attach wards to whoever happened to be in the same city."""
    assert capability_for({"institution": "Szpital Kliniczny", "city": "Olsztyn", "country": "PL"}) is None


def test_a_doctor_with_no_institution_gets_nothing() -> None:
    assert capability_for({"city": "Olsztyn", "country": "PL"}) is None


def test_the_result_carries_its_source_and_release() -> None:
    """A capability claim a reader cannot trace is the thing this codebase keeps
    removing; the register and its pinned version travel with the answer."""
    found = capability_for(
        {"institution": "Wojewódzki Specjalistyczny Szpital Dziecięcy im. prof. dr Stanisława Popowskiego",
         "city": "Olsztyn", "country": "PL"}
    )

    assert found is not None
    assert found.release == "2023_v2025_11"
    assert "gisco" in found.source
