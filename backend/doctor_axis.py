"""Which axis a directory row belongs to: clinical, or research.

The catalog is built from two different things that must never be presented as one.

- The **research axis** is how we DISCOVER people: every author of a paper about the
  disease becomes a row. That is the moat — for a disease with a few hundred published
  cases worldwide, the author list is the only cheap way to find anyone who has met it.
- The **clinical axis** is what a parent is actually asking for: a doctor who takes
  patients, in a named specialty, at an address.

Authorship alone says nothing about the second. Production proved it: a FD search
returned four Wrocław entries with no specialty at all, one of them affiliated to a
"Student Scientific Society of Otolaryngology" — co-authors of one case report, listed
to a newly diagnosed family as doctors to go to. Nobody fabricated that row; the
pipeline simply published an author record through a type called "doctor".

So the rule is a gate, not a label: a row reaches the public directory only when some
source OTHER than a publication says this is a clinician. Today that means

1. a verified clinical specialty — a NUCC code attached by ``specialty_enrich`` from
   NPPES (``high``/``medium`` confidence); or
2. a curated clinical specialty — the free-text ``specialty`` on a hand-added seed /
   consortium row, or the one a family typed when they recommended their own doctor.
   The finder never writes this field (Phase 0 cleared the PubMed role out of it), so a
   non-empty value here always came from a human; or
3. an explicit ``expert_reachable`` marker — the scientist who does not run a clinic but
   answers consult mail. Rare, always hand-set, and the one case a specialty check alone
   would wrongly drop.

Everything else stays in the database, stays reachable by direct profile link, and keeps
counting for the research-axis filters — it just stops being offered as a doctor.

Derived, never stored: the gate reads fields the row already carries, so it cannot drift
out of sync with a flow definition and applies identically to every producer — the
finder, the seed file, family submissions, and whatever imports come next.
"""

from __future__ import annotations

from typing import Any

# A specialty we are willing to show as the reason a row is in a clinical directory.
# "low" means the pipeline guessed (inference from affiliation/MeSH) and is never enough.
VERIFIED_SPECIALTY_CONFIDENCE: frozenset[str] = frozenset({"high", "medium"})

# Set only by a clinical source (curated seed or NPPES). ``expert_reachable`` is the
# "answers consult mail but runs no clinic" case, which must never be silently hidden.
CLINICAL_REACHABILITY: frozenset[str] = frozenset({"sees_patients", "expert_reachable"})


def verified_clinical_specialties(row: dict[str, Any]) -> list[dict[str, Any]]:
    """The row's canonical (NUCC-coded) specialties that carry high/medium confidence."""
    out: list[dict[str, Any]] = []
    for entry in row.get("clinicalSpecialties") or []:
        if not isinstance(entry, dict):
            continue
        if not str(entry.get("canonicalCode") or "").strip():
            continue
        if str(entry.get("confidence") or "").strip().lower() in VERIFIED_SPECIALTY_CONFIDENCE:
            out.append(entry)
    return out


def _curated_specialty(row: dict[str, Any]) -> str:
    """A human-entered specialty, as opposed to the mirror of a canonical one.

    ``_entry_to_public_doctor`` copies ``clinicalSpecialties[0].labelEn`` into the legacy
    ``specialty`` string, so a merely *inferred* NUCC row would otherwise sneak through
    the free-text branch. Anything that just repeats a canonical label is ignored here and
    judged on its confidence instead.
    """
    specialty = str(row.get("specialty") or "").strip()
    if not specialty:
        return ""
    mirrored = {
        str(entry.get("labelEn") or "").strip()
        for entry in row.get("clinicalSpecialties") or []
        if isinstance(entry, dict)
    }
    return "" if specialty in mirrored else specialty


def is_clinical_entry(row: dict[str, Any]) -> bool:
    """True when something other than a publication says this person is a clinician.

    See the module docstring for the three accepted anchors. A row that fails this is a
    research-axis record: real, useful for "who has published on this", and not a doctor
    a family can be sent to.
    """
    if not isinstance(row, dict):
        return False
    if verified_clinical_specialties(row):
        return True
    if _curated_specialty(row):
        return True
    return str(row.get("reachability") or "").strip() in CLINICAL_REACHABILITY


def clinical_entries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order-preserving filter down to the rows a patient-facing directory may show."""
    return [row for row in rows if is_clinical_entry(row)]
