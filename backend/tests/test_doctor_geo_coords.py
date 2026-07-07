"""Map coordinates for public doctor directory."""
from __future__ import annotations

from backend.doctor_geo_coords import coords_for_city_country, resolve_location


def test_sendai_japan_not_germany() -> None:
    lat, lng = coords_for_city_country("Sendai", "JP")
    assert lat > 35 and lng > 135


def test_seoul_korea_not_germany() -> None:
    lat, lng = coords_for_city_country("Seoul", "KR")
    assert lat > 37 and lng > 126


def test_unknown_city_uses_country_centroid() -> None:
    lat, lng = coords_for_city_country("—", "JP")
    assert lat > 30 and lng > 130


def test_distinct_countries_get_distinct_coords() -> None:
    jp = coords_for_city_country("—", "JP")
    kr = coords_for_city_country("—", "KR")
    assert jp != kr


def test_unknown_city_and_country_returns_none() -> None:
    """Neither city nor country known => no coordinates (map skips the pin, no wrong-continent default)."""
    assert coords_for_city_country("—", "—") is None
    assert coords_for_city_country("Nowhereville", "") is None
    assert coords_for_city_country("", "") is None


def test_gazetteer_places_city_without_country_and_reports_it() -> None:
    """Bucket B: a real city with no country should now land on the map + backfill the country."""
    loc = resolve_location("Moscow", "—")
    assert loc is not None
    lat, lng, iso2 = loc
    assert iso2 == "RU"
    assert 55 < lat < 56 and 36 < lng < 39  # Moscow RU, not Moscow, Idaho


def test_gazetteer_normalizes_postal_and_city_suffix() -> None:
    """Postal codes and a translated ' City' suffix must not block the lookup."""
    assert resolve_location("Daejeon 34141", "—")[2] == "KR"
    assert resolve_location("Wuhan City", "—")[2] == "CN"
    assert resolve_location("6220 Rabat", "—")[2] == "MA"


def test_gazetteer_rejects_non_cities() -> None:
    """Institution/department/street strings are not cities => no false pin."""
    assert resolve_location("Department of Ophthalmology", "—") is None
    assert resolve_location("Jacobs School of Medicine and Biomedical Sciences", "—") is None
    assert resolve_location("al. Powstańców Wlkp. 72", "—") is None


def test_gazetteer_country_scope_prevents_cross_country_match() -> None:
    """When the country IS known, a same-name city elsewhere must not hijack the pin."""
    # US Cambridge (MA) stays in the western hemisphere, not UK Cambridge.
    us = coords_for_city_country("Cambridge", "US")
    assert us is not None and us[1] < -50
    # A city absent from the known country falls back to that country's centroid, never Russia.
    jp = coords_for_city_country("Moscow", "JP")
    assert jp is not None and jp[1] > 120
