"""Attach European Reference Network membership to a doctor through their hospital.

This is the signal a publication database structurally cannot produce. A surgeon who
operates on children's skulls and does not publish is invisible to PubMed — and was
therefore being described by a vocabulary of authorship roles that did not fit him.
Meanwhile the network that exists precisely to answer "where in Europe do I go with
this rare disease" names his hospital.

ERNs publish membership at INSTITUTION level, never per clinician, so the claim this
makes is exactly that: this doctor practises at a centre the network recognises. It
deliberately does not say the doctor is personally accredited, because the source
does not say that.

Matching is on normalised name plus city, against aliases recorded in
``ern_centres.json``: the networks list centres under an English name while our
records hold the local one, so the alias list is data with a source rather than a
guess made at runtime.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_CENTRES_PATH = Path(__file__).resolve().parent / "ern_centres.json"


@dataclass(frozen=True, slots=True)
class ErnMembership:
    """One centre a doctor practises at, and where we read it."""

    ern: str
    role_detail: str
    centre: str
    city: str
    source_url: str
    verified_on: str


def _normalise(text: str) -> str:
    """Fold case, accents and punctuation so 'Wojewódzki' matches 'wojewodzki'."""
    folded = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


@lru_cache(maxsize=1)
def _centres() -> tuple[dict[str, Any], ...]:
    try:
        data = json.loads(_CENTRES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(data.get("centres") or [])


def _names_of(doctor: dict[str, Any]) -> list[str]:
    names = [str(doctor.get("institution") or "")]
    names += [str(p.get("name") or "") for p in doctor.get("practices") or [] if isinstance(p, dict)]
    return [n for n in names if n.strip()]


def memberships_for(doctor: dict[str, Any]) -> list[ErnMembership]:
    """Every recorded ERN centre this doctor practises at."""
    doctor_names = [_normalise(n) for n in _names_of(doctor)]
    if not doctor_names:
        return []
    doctor_city = _normalise(str(doctor.get("city") or ""))

    out: list[ErnMembership] = []
    for centre in _centres():
        centre_city = _normalise(str(centre.get("city") or ""))
        # City must agree when we know both: hospital names repeat across countries,
        # and a wrong match here would put a European accreditation on the wrong door.
        if doctor_city and centre_city and doctor_city != centre_city:
            continue
        candidates = [str(centre.get("name") or ""), *(centre.get("localAliases") or [])]
        if not any(_normalise(c) and _normalise(c) in name for c in candidates for name in doctor_names):
            continue
        out.append(
            ErnMembership(
                ern=str(centre.get("ern") or ""),
                role_detail=str(centre.get("roleDetail") or centre.get("role") or ""),
                centre=str(centre.get("name") or ""),
                city=str(centre.get("city") or ""),
                source_url=str(centre.get("sourceUrl") or ""),
                verified_on=str(centre.get("verifiedOn") or ""),
            )
        )
    return out
