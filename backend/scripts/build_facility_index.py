"""Build the facility capability index from the EU healthcare register.

Answers "which hospitals near me are equipped to treat this in a child" from an
official source, for any of the 32 countries GISCO covers — rather than from anyone's
knowledge of who the good doctors are. That distinction is the point: a named expert
does not generalise, a register does.

    python3 -m backend.scripts.build_facility_index            # default countries
    python3 -m backend.scripts.build_facility_index PL DE NL   # specific ones
    python3 -m backend.scripts.build_facility_index --check    # fail if stale

Writes backend/facility_index.json — only the derived fields, not the raw register,
so the repository carries a small reviewable artefact and the diff shows what
actually changed about hospitals rather than a re-serialised CSV.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from backend.facility_capability import capabilities_for, paediatric_capabilities_for
from backend.tools.eu_healthcare_facilities import GISCO_RELEASE, fetch_country

_OUT = pathlib.Path(__file__).resolve().parents[1] / "facility_index.json"
# Countries the directory currently serves families in. Adding one is a one-word change.
_DEFAULT_COUNTRIES = ("PL",)


def build(countries: tuple[str, ...]) -> dict:
    facilities = []
    for iso2 in countries:
        rows = fetch_country(iso2)
        if not rows:
            print(f"  {iso2}: no rows (fetch failed or empty)", file=sys.stderr)
            continue
        kept = 0
        for facility in rows:
            capabilities = sorted(capabilities_for(facility.wards))
            if not capabilities:
                continue  # a facility with nothing relevant is noise, not data
            facilities.append(
                {
                    "name": facility.name,
                    "city": facility.city,
                    "country": facility.country,
                    "lat": facility.lat,
                    "lon": facility.lon,
                    "capabilities": capabilities,
                    "paediatricCapabilities": sorted(paediatric_capabilities_for(facility.wards)),
                    "wardCount": len(facility.wards),
                }
            )
            kept += 1
        print(f"  {iso2}: {kept} relevant of {len(rows)} facilities")

    facilities.sort(key=lambda f: (f["country"], f["city"], f["name"]))
    return {
        "_comment": [
            "Derived from the EU healthcare facility register (GISCO). Do not edit by",
            "hand — rebuild with `python3 -m backend.scripts.build_facility_index`.",
            "Only facilities with at least one disease-relevant ward are kept.",
        ],
        "source": "https://gisco-services.ec.europa.eu/pub/healthcare/",
        "release": GISCO_RELEASE,
        "countries": list(countries),
        "facilities": facilities,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("countries", nargs="*", help="ISO2 codes (default: PL)")
    parser.add_argument("--check", action="store_true", help="fail if the file is out of date")
    args = parser.parse_args()

    countries = tuple(c.upper() for c in args.countries) or _DEFAULT_COUNTRIES
    index = build(countries)
    rendered = json.dumps(index, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        current = _OUT.read_text(encoding="utf-8") if _OUT.exists() else ""
        if current != rendered:
            print("facility_index.json is out of date — rebuild it", file=sys.stderr)
            return 1
        print("facility_index.json is current")
        return 0

    _OUT.write_text(rendered, encoding="utf-8")
    print(f"\nwrote {_OUT.name}: {len(index['facilities'])} facilities, release {GISCO_RELEASE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
