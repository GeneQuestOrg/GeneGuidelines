from __future__ import annotations

from backend.flows.doctor_finder.country_continent_table import continent_for_iso_alpha2, load_iso_alpha2_to_continent


def test_load_covers_common_iso2() -> None:
    m = load_iso_alpha2_to_continent()
    assert len(m) >= 200
    assert m["PL"] == "Europe"
    assert m["BD"] == "Asia"
    assert m["BR"] == "South America"
    assert m["CA"] == "North America"


def test_tr_override_europe() -> None:
    assert continent_for_iso_alpha2("TR") == "Europe"


def test_continent_for_iso_rejects_garbage() -> None:
    assert continent_for_iso_alpha2(None) is None
    assert continent_for_iso_alpha2("") is None
    assert continent_for_iso_alpha2("PLN") is None
