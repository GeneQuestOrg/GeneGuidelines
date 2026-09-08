"""What KIND of case a doctor handles — not just whether they have touched the disease.

A parent whose child has craniofacial fibrous dysplasia is not asking "has this
doctor seen FD". They are asking "is this the person for a skull in a child". FD
splits into presentations that are handled by entirely different people: the
craniofacial surgeon, the orthopaedic surgeon managing a femur, the endocrinologist
managing McCune-Albright. A directory that shows all three identically leaves the
family to guess, and guessing wrong costs months.

Everything here is DERIVED from fields already stored — publication titles, clinical
specialty, institution — so the same input always yields the same tags and a re-run
reproduces them exactly. Nothing is inferred by a model and nothing is invented: each
tag carries the text it came from, so the page can show why it is there and a reader
can disagree with it.

Deliberately conservative. A missing tag costs a family one extra question; a wrong
one sends them to the wrong clinic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Anatomy that places FD in the skull and face. These are the words that appear in
# real titles ("Fibrous Dysplasia of the Ethmoid Bone", "Recurrent Orbital
# Inflammation Due to Fibrous Dysplasia") rather than a textbook list.
_CRANIOFACIAL = (
    "craniofacial", "cranio-facial", "skull", "cranial", "orbit", "orbital",
    "ethmoid", "sphenoid", "maxilla", "maxillary", "mandible", "mandibular",
    "zygoma", "zygomatic", "temporal bone", "frontal bone", "sinus", "nasal",
    "facial", "optic nerve", "skull base", "midface",
)
# The appendicular skeleton: the other surgical specialty entirely.
_SKELETAL = (
    "femur", "femoral", "tibia", "tibial", "humerus", "long bone", "hip",
    "shepherd's crook", "fracture", "limb", "scoliosis", "spine", "vertebral",
)
# McCune-Albright's endocrine axis, managed by endocrinologists, not surgeons.
_ENDOCRINE = (
    "precocious puberty", "endocrin", "acromegaly", "growth hormone", "thyroid",
    "cushing", "hyperthyroid", "phosphaturia", "hypophosphatemia", "rickets",
    "mccune-albright", "mccune albright",
)
_PAEDIATRIC = (
    "pediatric", "paediatric", "child", "children", "infant", "adolescent",
    "juvenile", "boy", "girl", "dziecię", "dzieci",
)

_SPECIALTY_SCOPE = {
    "craniofacial": ("maxillofacial", "oral and maxillofacial", "craniofacial", "oral surgery"),
    "endocrine": ("endocrinolog",),
    "skeletal": ("orthopaed", "orthoped"),
}

_ORDER = ("craniofacial", "skeletal", "endocrine", "paediatric")


@dataclass(frozen=True, slots=True)
class ScopeTag:
    """One scope claim and the exact text it was read from."""

    key: str
    basis: str


def _matches(haystack: str, needles: tuple[str, ...]) -> str | None:
    low = haystack.lower()
    for needle in needles:
        if needle in low:
            return needle
    return None


def _age_from_title(title: str) -> bool:
    """"Diagnosed in a 10-Year-Old Patient" is a paediatric case; 40-year-old is not."""
    match = re.search(r"\b(\d{1,2})[- ]year[- ]old\b", title.lower())
    return bool(match and int(match.group(1)) < 18)


def derive_scope(doctor: dict[str, Any]) -> list[ScopeTag]:
    """Scope tags for one doctor, strongest evidence first, each with its basis.

    Publication titles outrank specialty, and specialty outranks institution: what
    someone published about a disease is closer evidence than the department they sit
    in. Only the first basis for a given tag is kept, so the reason shown is the best
    one available.
    """
    found: dict[str, str] = {}

    def record(key: str, basis: str) -> None:
        found.setdefault(key, basis)

    for publication in doctor.get("publications") or []:
        title = str(publication.get("title") or "")
        if not title:
            continue
        for key, vocabulary in (
            ("craniofacial", _CRANIOFACIAL),
            ("skeletal", _SKELETAL),
            ("endocrine", _ENDOCRINE),
        ):
            hit = _matches(title, vocabulary)
            if hit:
                record(key, f'„{hit}" — {title}')
        if _matches(title, _PAEDIATRIC) or _age_from_title(title):
            record("paediatric", title)

    specialty = str(doctor.get("specialty") or "")
    if specialty:
        for key, needles in _SPECIALTY_SCOPE.items():
            hit = _matches(specialty, needles)
            if hit:
                record(key, specialty)

    # Institution is used for age only. A children's hospital is unambiguous about who
    # it treats; a department name says little about which bones.
    institution = str(doctor.get("institution") or "")
    if institution and _matches(institution, _PAEDIATRIC + ("wssd",)):
        record("paediatric", institution)

    return [ScopeTag(key=key, basis=found[key]) for key in _ORDER if key in found]


def scope_keys(doctor: dict[str, Any]) -> list[str]:
    return [tag.key for tag in derive_scope(doctor)]
