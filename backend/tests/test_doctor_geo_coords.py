"""Map coordinates for public doctor directory."""
from __future__ import annotations

from backend.doctor_geo_coords import coords_for_city_country


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
