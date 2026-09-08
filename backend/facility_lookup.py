"""Match a doctor to the hospital they practise in, in the EU facility register.

The register knows what a place is equipped for; our records know where a doctor
works. Joining them answers the question a family actually has — "is there somewhere
near me equipped to treat this in a child, and who is there" — from official data
rather than from anyone's reputation.

Matching is on city plus a distinctive-token overlap of the names. Hospital names are
long, officially punctuated and inconsistently abbreviated between sources ("WSSD
Olsztyn" against "WOJEWÓDZKI SPECJALISTYCZNY SZPITAL DZIECIĘCY IM. PROF. DR
STANISŁAWA POPOWSKIEGO"), so an exact match finds almost nothing while a loose one
would attach a hospital's capabilities to the wrong doctor. The threshold is
deliberately strict and a near-miss yields nothing: an unmatched doctor loses a badge,
a mismatched one gets a claim about a building they have never worked in.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_INDEX_PATH = Path(__file__).resolve().parent / "facility_index.json"

# Words that appear in most Polish hospital names and so carry no identifying power.
_STOPWORDS = {
    "szpital", "szpitala", "specjalistyczny", "wojewodzki", "samodzielny", "publiczny",
    "zaklad", "opieki", "zdrowotnej", "zespol", "centrum", "imienia", "prof", "dr",
    "im", "sp", "z", "o", "sa", "spolka", "ograniczona", "odpowiedzialnoscia",
    "uniwersytecki", "kliniczny", "nr", "w", "instytut", "medyczny", "publicznych",
    "zakladow", "hospital", "clinic", "medical", "university", "of", "the", "and",
}
_MIN_TOKEN_LEN = 4
_MIN_SHARED_TOKENS = 2


@dataclass(frozen=True, slots=True)
class FacilityCapability:
    """What the doctor's hospital is equipped for, per the register."""

    name: str
    city: str
    capabilities: tuple[str, ...]
    paediatric_capabilities: tuple[str, ...]
    source: str
    release: str


def _normalise(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


def _tokens(name: str) -> set[str]:
    return {
        token
        for token in _normalise(name).split()
        if len(token) >= _MIN_TOKEN_LEN and token not in _STOPWORDS
    }


@lru_cache(maxsize=1)
def _index() -> dict[str, Any]:
    try:
        return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _doctor_names(doctor: dict[str, Any]) -> list[str]:
    names = [str(doctor.get("institution") or "")]
    names += [
        str(p.get("name") or "")
        for p in doctor.get("practices") or []
        if isinstance(p, dict)
    ]
    return [n for n in names if n.strip()]


def _nearest(doctor: dict[str, Any], leaders: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The tied facility closest to the doctor's recorded coordinates, if that is knowable."""
    try:
        doctor_lat = float(doctor["lat"])
        doctor_lon = float(doctor["lng"])
    except (KeyError, TypeError, ValueError):
        return None

    def distance(facility: dict[str, Any]) -> float | None:
        try:
            return (float(facility["lat"]) - doctor_lat) ** 2 + (
                float(facility["lon"]) - doctor_lon
            ) ** 2
        except (KeyError, TypeError, ValueError):
            return None

    ranked = [(d, f) for f in leaders if (d := distance(f)) is not None]
    if len(ranked) < len(leaders):
        return None  # an incomplete comparison is not a comparison
    ranked.sort(key=lambda pair: pair[0])
    return ranked[0][1]


def capability_for(doctor: dict[str, Any]) -> FacilityCapability | None:
    """The registered facility this doctor practises in, or None when unsure."""
    index = _index()
    facilities = index.get("facilities") or []
    if not facilities:
        return None

    doctor_city = _normalise(str(doctor.get("city") or ""))
    doctor_country = str(doctor.get("country") or "").upper()
    candidates = [_tokens(name) for name in _doctor_names(doctor)]
    candidates = [c for c in candidates if c]
    if not candidates:
        return None

    # The city name itself carries no identifying power — city equality is already
    # required — and counting it inflated a one-token coincidence into an apparent
    # two-token match. "Children's hospital in Olsztyn" would then match on
    # "children's" alone, which is right where there is one and wrong where there are
    # two.
    city_tokens = set(doctor_city.split())

    scored: list[tuple[int, dict[str, Any]]] = []
    for facility in facilities:
        if doctor_country and str(facility.get("country") or "").upper() != doctor_country:
            continue
        if doctor_city and _normalise(str(facility.get("city") or "")) != doctor_city:
            continue
        facility_tokens = _tokens(str(facility.get("name") or "")) - city_tokens
        if not facility_tokens:
            continue
        shared = max(len(tokens - city_tokens & facility_tokens) for tokens in candidates)
        if shared:
            scored.append((shared, facility))

    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top_score = scored[0][0]
    leaders = [facility for score, facility in scored if score == top_score]

    if len(leaders) == 1:
        facility = leaders[0]
    else:
        # Several hospitals in the city share the same generic word — "dziecięcy"
        # names half of them. Names cannot separate these, so geography does: a
        # practice address sits at its own hospital, not at a rival across town. With
        # no coordinates there is nothing left to decide on, and guessing would put a
        # ward on the wrong door.
        nearest = _nearest(doctor, leaders)
        if nearest is None:
            return None
        facility = nearest
    return FacilityCapability(
        name=str(facility.get("name") or ""),
        city=str(facility.get("city") or ""),
        capabilities=tuple(facility.get("capabilities") or []),
        paediatric_capabilities=tuple(facility.get("paediatricCapabilities") or []),
        source=str(_index().get("source") or ""),
        release=str(_index().get("release") or ""),
    )
