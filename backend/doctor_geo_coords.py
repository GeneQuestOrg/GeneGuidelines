"""Map city / ISO-2 country codes to approximate lat/lng for the public doctor directory."""
from __future__ import annotations

import re
from functools import lru_cache

try:
    import pycountry
except ImportError:  # pragma: no cover
    pycountry = None  # type: ignore[assignment]

try:
    import geonamescache
except ImportError:  # pragma: no cover
    geonamescache = None  # type: ignore[assignment]

_CONTINENT_CENTROIDS: dict[str, tuple[float, float]] = {
    "Africa": (8.0, 20.0),
    "Asia": (34.0, 108.0),
    "Europe": (50.0, 15.0),
    "North America": (45.0, -100.0),
    "South America": (-15.0, -60.0),
    "Oceania": (-22.0, 133.0),
}

# Finer centroids for countries that appear often in PubMed / Doctor Finder.
_COUNTRY_OVERRIDES: dict[str, tuple[float, float]] = {
    "PL": (52.0, 19.0),
    "DE": (51.1657, 10.4515),
    "NL": (52.16, 5.0),
    "BE": (50.8503, 4.3517),
    "FR": (46.2276, 2.2137),
    "GB": (54.0, -2.0),
    "IE": (53.4129, -8.2439),
    "IT": (41.8719, 12.5674),
    "ES": (40.4637, -3.7492),
    "PT": (39.3999, -8.2245),
    "CH": (46.8182, 8.2275),
    "AT": (47.5162, 14.5501),
    "SE": (60.1282, 18.6435),
    "NO": (60.472, 8.4689),
    "DK": (56.2639, 9.5018),
    "FI": (61.9241, 25.7482),
    "CZ": (49.8175, 15.473),
    "HU": (47.1625, 19.5033),
    "RO": (45.9432, 24.9668),
    "GR": (39.0742, 21.8243),
    "TR": (38.9637, 35.2433),
    "US": (39.8283, -98.5795),
    "CA": (56.1304, -106.3468),
    "MX": (23.6345, -102.5528),
    "BR": (-14.235, -51.9253),
    "AR": (-38.4161, -63.6167),
    "AU": (-25.2744, 133.7751),
    "NZ": (-40.9006, 174.886),
    "JP": (36.2048, 138.2529),
    "KR": (35.9078, 127.7669),
    "CN": (35.8617, 104.1954),
    "TW": (23.6978, 120.9605),
    "HK": (22.3193, 114.1694),
    "SG": (1.3521, 103.8198),
    "IN": (20.5937, 78.9629),
    "IL": (31.0461, 34.8516),
    "AE": (23.4241, 53.8478),
    "SA": (23.8859, 45.0792),
    "ZA": (-30.5595, 22.9375),
    "EG": (26.8206, 30.8025),
    "RU": (61.524, 105.3188),
    "UA": (48.3794, 31.1656),
}

_CITY_COORDS: dict[str, tuple[float, float]] = {
    "Olsztyn": (53.778, 20.48),
    "Poznań": (52.408, 16.934),
    "Poznan": (52.408, 16.934),
    "Zielona Góra": (51.935, 15.506),
    "Zielona Gora": (51.935, 15.506),
    "Warsaw": (52.229, 21.012),
    "Warszawa": (52.229, 21.012),
    "Kraków": (50.0647, 19.9450),
    "Krakow": (50.0647, 19.9450),
    "Gdańsk": (54.3520, 18.6466),
    "Gdansk": (54.3520, 18.6466),
    "Wrocław": (51.1079, 17.0385),
    "Wroclaw": (51.1079, 17.0385),
    "Łódź": (51.7592, 19.4550),
    "Lodz": (51.7592, 19.4550),
    "Berlin": (52.52, 13.405),
    "Munich": (48.1351, 11.582),
    "München": (48.1351, 11.582),
    "Hamburg": (53.5511, 9.9937),
    "Frankfurt": (50.1109, 8.6821),
    "London": (51.5074, -0.1278),
    "Paris": (48.8566, 2.3522),
    "Amsterdam": (52.3676, 4.9041),
    "Leiden": (52.166, 4.49),
    "Rome": (41.902, 12.496),
    "Roma": (41.902, 12.496),
    "Milan": (45.4642, 9.19),
    "Milano": (45.4642, 9.19),
    "Madrid": (40.4168, -3.7038),
    "Barcelona": (41.3851, 2.1734),
    "Boston": (42.36, -71.06),
    "New York": (40.7128, -74.006),
    "Toronto": (43.6532, -79.3832),
    "Montreal": (45.5017, -73.5673),
    "Sydney": (-33.8688, 151.2093),
    "Melbourne": (-37.8136, 144.9631),
    "Tokyo": (35.6762, 139.6503),
    "Sendai": (38.2682, 140.8694),
    "Osaka": (34.6937, 135.5023),
    "Kyoto": (35.0116, 135.7681),
    "Nagoya": (35.1815, 136.9066),
    "Seoul": (37.5665, 126.9780),
    "Busan": (35.1796, 129.0756),
    "Singapore": (1.3521, 103.8198),
    "Hong Kong": (22.3193, 114.1694),
    "Taipei": (25.033, 121.5654),
    "Beijing": (39.9042, 116.4074),
    "Shanghai": (31.2304, 121.4737),
    "Mumbai": (19.076, 72.8777),
    "Delhi": (28.7041, 77.1025),
    "Bangkok": (13.7563, 100.5018),
    "Tel Aviv": (32.0853, 34.7818),
    "Dubai": (25.2048, 55.2708),
    "São Paulo": (-23.5505, -46.6333),
    "Sao Paulo": (-23.5505, -46.6333),
    "Mexico City": (19.4326, -99.1332),
}

_CITY_COORDS_LOWER = {k.lower(): v for k, v in _CITY_COORDS.items()}


def normalize_country_iso2(country: str) -> str | None:
    """Return ISO-3166-1 alpha-2 for a code or country name."""
    raw = (country or "").strip()
    if not raw or raw == "—":
        return None
    if len(raw) == 2 and raw.isalpha():
        return raw.upper()
    if pycountry is not None:
        try:
            match = pycountry.countries.lookup(raw)
            return str(match.alpha_2).upper()
        except LookupError:
            pass
    return None


@lru_cache(maxsize=1)
def _iso2_country_coords() -> dict[str, tuple[float, float]]:
    """ISO-2 → lat/lng: explicit overrides plus continent centroid fallback."""
    out: dict[str, tuple[float, float]] = {}
    try:
        from .flows.doctor_finder.country_continent_table import load_iso_alpha2_to_continent
    except ImportError:
        from flows.doctor_finder.country_continent_table import load_iso_alpha2_to_continent

    for iso2, continent in load_iso_alpha2_to_continent().items():
        centroid = _CONTINENT_CENTROIDS.get(continent)
        if centroid is not None:
            out[iso2] = centroid
    out.update(_COUNTRY_OVERRIDES)
    return out


def _norm_city_name(city: str) -> str:
    """Lowercase a city string and strip postal codes / punctuation for gazetteer lookup."""
    s = (city or "").strip().lower()
    s = re.sub(r"\d+", " ", s)          # postal codes ("Daejeon 34141", "6220 Rabat")
    s = re.sub(r"[^\w\s\-]", " ", s)    # punctuation
    s = re.sub(r"\s+", " ", s).strip()
    return s


@lru_cache(maxsize=1)
def _city_gazetteer() -> tuple[dict[str, tuple[float, float, str]], dict[tuple[str, str], tuple[float, float]]]:
    """Build a GeoNames city index for placing clinicians whose affiliation gave a city but no country.

    Returns ``(by_name, by_name_country)`` where the global ``by_name`` keeps the highest-population
    place per name (so ambiguous names like "Moscow"/"Washington"/"Cambridge" resolve to the dominant
    city) and ``by_name_country`` lets callers that already know the country avoid a same-name city on
    another continent. Primary GeoNames names only (no alternate names) — the extra localized aliases
    ~10x the index for +2% coverage that the hand-curated ``_CITY_COORDS`` above already handles.
    """
    by_name: dict[str, tuple[float, float, str]] = {}
    by_name_country: dict[tuple[str, str], tuple[float, float]] = {}
    if geonamescache is None:  # pragma: no cover - dependency always present in prod
        return by_name, by_name_country
    name_pop: dict[str, int] = {}
    nc_pop: dict[tuple[str, str], int] = {}
    for c in geonamescache.GeonamesCache().get_cities().values():
        try:
            lat = float(c["latitude"])
            lng = float(c["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        cc = str(c.get("countrycode") or "").upper()
        pop = int(c.get("population") or 0)
        k = _norm_city_name(str(c.get("name") or ""))
        if len(k) < 3 or not any(ch.isalpha() for ch in k):
            continue
        if pop > name_pop.get(k, -1):
            name_pop[k] = pop
            by_name[k] = (lat, lng, cc)
        if cc:
            key = (k, cc)
            if pop > nc_pop.get(key, -1):
                nc_pop[key] = pop
                by_name_country[key] = (lat, lng)
    return by_name, by_name_country


def _gazetteer_lookup(city: str, iso2: str | None) -> tuple[float, float, str] | None:
    """Resolve a city to (lat, lng, iso2) via GeoNames, scoped to ``iso2`` when the country is known.

    When the country is known we ONLY accept a same-country match (else return None so the caller
    falls back to the country centroid) — this prevents a US "Cambridge" from landing in the UK.
    When the country is unknown (the bucket this feature targets) we take the global highest-population
    match and report its country so the caller can backfill it.
    """
    by_name, by_name_country = _city_gazetteer()

    def _try(key: str) -> tuple[float, float, str] | None:
        if len(key) < 3:
            return None
        if iso2:
            e = by_name_country.get((key, iso2))
            return (e[0], e[1], iso2) if e is not None else None
        return by_name.get(key)

    k = _norm_city_name(city)
    hit = _try(k)
    if hit is None and k.endswith(" city"):
        hit = _try(k[:-5].strip())
    return hit


def resolve_location(city: str, country: str) -> tuple[float, float, str | None] | None:
    """Approximate map coords for a clinician plus the resolved ISO-2 country (if any), or None.

    Order of trust: hand-curated ``_CITY_COORDS`` → GeoNames gazetteer (country-scoped when the
    country is known, else global highest-population) → country override/centroid. Returns ``None``
    when neither a city nor a usable country is known, so the map omits the pin instead of guessing.
    The third tuple element lets callers backfill a country that was missing on the source record.
    """
    iso2 = normalize_country_iso2(country)

    city_key = (city or "").strip()
    if city_key and city_key != "—":
        hit = _CITY_COORDS_LOWER.get(city_key.lower())
        if hit is not None:
            return (hit[0], hit[1], iso2)
        gaz = _gazetteer_lookup(city_key, iso2)
        if gaz is not None:
            return gaz

    if iso2:
        hit = _iso2_country_coords().get(iso2)
        if hit is not None:
            return (hit[0], hit[1], iso2)

        try:
            from .flows.doctor_finder.country_continent_table import continent_for_iso_alpha2
        except ImportError:
            from flows.doctor_finder.country_continent_table import continent_for_iso_alpha2

        continent = continent_for_iso_alpha2(iso2)
        if continent and continent in _CONTINENT_CENTROIDS:
            centroid = _CONTINENT_CENTROIDS[continent]
            return (centroid[0], centroid[1], iso2)

    return None


def coords_for_city_country(city: str, country: str) -> tuple[float, float] | None:
    """Approximate map coordinates for a clinician card, or ``None`` when the location is unknown.

    Thin wrapper over :func:`resolve_location` for callers that only need coordinates (see that
    function for the resolution order and the ``None`` semantics that keep unlocated clinicians off
    the map instead of at an arbitrary default).
    """
    loc = resolve_location(city, country)
    return None if loc is None else (loc[0], loc[1])
