"""What a hospital is equipped to do, read from its wards.

The scope axis (backend/doctor_scope.py) says which presentation a DOCTOR handles.
This says which presentation a PLACE is equipped for, and deliberately uses the same
vocabulary, because a family reading "skull and face · children" next to a name and
next to a hospital should be reading the same claim about both.

It matters because the two are independent. A surgeon can be the right person and
work somewhere without the ward; a hospital can have the ward and no one listed. Six
hospitals in Poland have a paediatric maxillofacial ward — that is a finding about
the country, reproducible from an official register, and it does not depend on
anybody's opinion of any particular professor.

Ward names arrive in each country's own official nomenclature, so the vocabularies
are per-language and additive: an unmatched ward yields no capability rather than a
guess.
"""

from __future__ import annotations

import re
import unicodedata

# Keys are shared with doctor_scope so both axes read as one language.
_PATTERNS: dict[str, tuple[str, ...]] = {
    "craniofacial": (
        # Polish official ward names
        "szczekowo twarzow", "chirurgii szczekowej", "otolaryngolog", "laryngolog",
        "neurochirurg", "okulistyczn",
        # English / other
        "maxillofacial", "craniofacial", "otolaryngolog", "otorhinolaryngolog",
        "neurosurg", "ophthalm", "ent ",
    ),
    "skeletal": (
        "ortopedyczn", "urazowo ortopedyczn", "chirurgii urazowej",
        "orthopaed", "orthoped", "trauma surgery",
    ),
    "endocrine": (
        "endokrynolog", "diabetolog",
        "endocrinolog",
    ),
}

# A ward may be adult or paediatric; the distinction is the whole question for a
# parent, so it is a capability of its own rather than a modifier.
_PAEDIATRIC = (
    "dla dzieci", "dzieciec", "pediatryczn", "noworodk",
    "paediatric", "pediatric", "children", "neonat",
)


def _normalise(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


def capabilities_for(wards: tuple[str, ...] | list[str]) -> set[str]:
    """Capability keys a facility's wards support. Unmatched wards contribute nothing."""
    found: set[str] = set()
    for ward in wards:
        normalised = f" {_normalise(ward)} "
        for key, needles in _PATTERNS.items():
            if any(needle in normalised for needle in needles):
                found.add(key)
        if any(needle in normalised for needle in _PAEDIATRIC):
            found.add("paediatric")
    return found


def paediatric_capabilities_for(wards: tuple[str, ...] | list[str]) -> set[str]:
    """Capabilities the facility offers TO CHILDREN specifically.

    "Has a maxillofacial ward" and "has a maxillofacial ward for children" are
    different answers to a parent, and conflating them is the kind of near-miss that
    sends a family to the wrong hospital. Only wards that are themselves paediatric
    count here.
    """
    found: set[str] = set()
    for ward in wards:
        normalised = f" {_normalise(ward)} "
        if not any(needle in normalised for needle in _PAEDIATRIC):
            continue
        for key, needles in _PATTERNS.items():
            if any(needle in normalised for needle in needles):
                found.add(key)
    return found
