"""Official EU register of healthcare facilities, as a source of institutional capability.

The doctor directory is built from PubMed, which sees authors. It cannot see a
hospital's wards — so it cannot answer the question a family actually asks: who, near
me, is equipped to treat this in a child. Establishing that one particular professor
is excellent does not generalise; a register does.

GISCO (the Commission's geographic information service) publishes healthcare
facilities for 32 countries as per-country CSV, in dated releases:

    https://gisco-services.ec.europa.eu/pub/healthcare/<release>/csv/<ISO2>.csv

Two properties make it usable as infrastructure rather than a one-off scrape. The
release is versioned and pinned here, so a re-run yields the same rows and an upgrade
is a deliberate, diffable act. And `list_specs` carries the facility's WARDS in the
country's own official nomenclature — for Poland, 665 of 682 hospitals — which is the
capability axis a citation database structurally cannot supply.

Field coverage varies by country: `cap_beds`, `facility_type` and `url` are empty for
Poland while `list_specs` is populated. Anything read from here must therefore treat
a missing field as unknown, never as zero.
"""

from __future__ import annotations

import csv
import io
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Pinned deliberately. Bumping it is a change to what the site claims about hospitals,
# so it should show up in a diff and be re-verified, not drift in silently.
GISCO_RELEASE = "2023_v2025_11"
_CSV_URL = "https://gisco-services.ec.europa.eu/pub/healthcare/{release}/csv/{iso2}.csv"
_USER_AGENT = "GeneQuestFoundation/1.0 (https://genequest.org; darek@genequest.org)"
_TIMEOUT_SEC = 120

_MISSING = {"", "na", "n/a", "-", "none", "null"}


@dataclass(frozen=True, slots=True)
class Facility:
    """One hospital site. Empty strings mean the country did not supply the field."""

    name: str
    site: str
    city: str
    country: str
    lat: float | None
    lon: float | None
    wards: tuple[str, ...]
    url: str
    ref_date: str


def _clean(value: str | None) -> str:
    text = (value or "").strip()
    return "" if text.lower() in _MISSING else text


def _float(value: str | None) -> float | None:
    try:
        return float(_clean(value))
    except ValueError:
        return None


def parse_country_csv(text: str, iso2: str) -> list[Facility]:
    """Parse one country's CSV. Tolerates the BOM the files ship with."""
    rows = csv.DictReader(io.StringIO(text))
    out: list[Facility] = []
    for row in rows:
        # The first column arrives as "﻿id"; every other key is clean.
        clean_row = {key.lstrip("﻿"): value for key, value in row.items() if key}
        name = _clean(clean_row.get("hospital_name"))
        if not name:
            continue
        wards = tuple(
            part.strip()
            for part in _clean(clean_row.get("list_specs")).split("|")
            if part.strip()
        )
        out.append(
            Facility(
                name=name,
                site=_clean(clean_row.get("site_name")),
                city=_clean(clean_row.get("city")),
                country=_clean(clean_row.get("cntr_id")) or iso2.upper(),
                lat=_float(clean_row.get("lat")),
                lon=_float(clean_row.get("lon")),
                wards=wards,
                url=_clean(clean_row.get("url")),
                ref_date=_clean(clean_row.get("ref_date")),
            )
        )
    return out


def fetch_country(iso2: str, release: str = GISCO_RELEASE) -> list[Facility]:
    """Facilities for one country, or [] when the file cannot be read.

    Never raises: a country that fails to download leaves the index thinner, it does
    not fail whatever was building it.
    """
    url = _CSV_URL.format(release=release, iso2=iso2.upper())
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SEC) as response:
            text = response.read().decode("utf-8-sig", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.warning("gisco: could not fetch %s (%s): %s", iso2, release, exc)
        return []
    return parse_country_csv(text, iso2)
