"""ISO 3166-1 alpha-2 → continent labels used by Doctor Finder (UI select).

Data is loaded from ``data/all.csv`` (lukes/ISO-3166-Countries-with-Regional-Codes, MIT).
Americas are split into **North America** and **South America** to match the frontend
``CONTINENTS`` list. A tiny override map adjusts a few transboundary countries for
clinical search expectations (e.g. Türkiye → Europe filter).
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent / "data" / "all.csv"

# Applied after CSV-derived rows (alpha-2 upper).
_CONTINENT_OVERRIDES: dict[str, str] = {
    "TR": "Europe",
    "CY": "Europe",
}


def _americas_continent(sub_region: str, intermediate: str) -> str | None:
    sub = (sub_region or "").strip()
    interm = (intermediate or "").strip()
    if sub == "Northern America":
        return "North America"
    if interm == "South America":
        return "South America"
    if interm == "Caribbean" or sub == "Central America" or interm == "Central America":
        return "North America"
    if sub == "Latin America and the Caribbean":
        if interm == "South America":
            return "South America"
        if interm in {"Caribbean", "Central America"}:
            return "North America"
        if interm:
            return "South America"
        return "North America"
    return "South America"


def _row_to_continent(region: str, sub_region: str, intermediate: str) -> str | None:
    r = (region or "").strip()
    if r in {"Africa", "Asia", "Europe", "Oceania"}:
        return r
    if r == "Americas":
        return _americas_continent(sub_region, intermediate)
    return None


@lru_cache(maxsize=1)
def load_iso_alpha2_to_continent() -> dict[str, str]:
    """Return uppercased ISO-2 → continent name (Africa, Asia, Europe, North America, Oceania, South America)."""
    out: dict[str, str] = {}
    with _DATA_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            alpha2 = (row.get("alpha-2") or "").strip().upper()
            if len(alpha2) != 2:
                continue
            cont = _row_to_continent(
                row.get("region") or "",
                row.get("sub-region") or "",
                row.get("intermediate-region") or "",
            )
            if cont:
                out[alpha2] = cont
    out.update({k.upper(): v for k, v in _CONTINENT_OVERRIDES.items()})
    return out


def continent_for_iso_alpha2(code: str | None) -> str | None:
    """Map ISO-3166-1 alpha-2 to continent, or None if unknown."""
    if not code:
        return None
    key = str(code).strip().upper()
    if len(key) != 2 or not key.isalpha():
        return None
    return load_iso_alpha2_to_continent().get(key)
