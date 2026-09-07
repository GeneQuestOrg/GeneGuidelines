"""Every publication we attribute to a named doctor must be one they actually wrote.

Four of the five seeded publications were fabricated: real PMIDs carrying invented
titles, attached to real, named scientists who did not write them.

    37001122  claimed "Orthognathic surgery in patients with craniofacial bony
              lesions" — is actually a scoping review of ventilator weaning
              education for ICU nurses, by Kimura, Barroga and Hayashi
    34964677  attributed to Appelman-Dijkstra — authors are Huzum, Antoniu, Dragomir
    25719192  attributed to Riminucci — the GeneReviews chapter, by Szymczuk,
              Florenzano, de Castro, Collins and Boyce
    32119988  attributed to Hsiao — a paper on epigenetic alterations in a cell
              line, by Karaman, Zeybel and Ozden

Two of those people are scientists the foundation is preparing to show this product
to. Publishing a citation someone did not write, under their name, is the most
damaging thing this directory can do — worse than listing nobody.

CI has no network, so this cannot re-check PubMed. Instead every seeded PMID must
appear below, which forces whoever adds one to verify it first and record that they
did. `python3 -m backend.scripts.validate_seeded_citations` does the live check.
"""

from __future__ import annotations

import json
import pathlib

# PMID -> what PubMed says, checked against esummary on 2026-09-07.
# Add an entry only after running the validation script and reading the result.
VERIFIED: dict[str, str] = {
    # Appelman-Dijkstra N is a listed author of the 2019 best-practice consensus.
    "31196103": "Best practice management guidelines for fibrous dysplasia/McCune-Albright syndrome",
}

_SEED = pathlib.Path(__file__).resolve().parents[1] / "content_doctors.json"


def _seeded_publications() -> list[tuple[str, str, str]]:
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    rows = data.get("doctors", data) if isinstance(data, dict) else data
    return [
        (str(doc.get("slug", "?")), str(pub.get("pmid", "")), str(pub.get("title", "")))
        for doc in rows
        for pub in (doc.get("publications") or [])
    ]


def test_no_seeded_publication_is_unverified() -> None:
    unverified = [
        f"{slug}: PMID {pmid} — {title[:60]}"
        for slug, pmid, title in _seeded_publications()
        if pmid not in VERIFIED
    ]

    assert not unverified, (
        "these seeded publications are not in the verified list:\n  "
        + "\n  ".join(unverified)
        + "\n\nRun `python3 -m backend.scripts.validate_seeded_citations` and add the "
        "PMID to VERIFIED only if PubMed confirms both the title and the authorship."
    )


def test_the_recorded_title_matches_what_pubmed_says() -> None:
    """A right PMID with an invented title is still a fabricated citation — three of
    the four removed here were exactly that, and the PMID alone would not catch it."""
    wrong = [
        f"{slug}: PMID {pmid} says {title!r}, PubMed says {VERIFIED[pmid]!r}"
        for slug, pmid, title in _seeded_publications()
        if pmid in VERIFIED and title.strip().lower() != VERIFIED[pmid].strip().lower()
    ]

    assert not wrong, "seeded titles disagree with PubMed:\n  " + "\n  ".join(wrong)


def test_the_known_fabrications_have_not_come_back() -> None:
    seeded = {pmid for _, pmid, _ in _seeded_publications()}

    for pmid in ("37001122", "34964677", "25719192", "32119988"):
        assert pmid not in seeded, f"PMID {pmid} was a verified fabrication; it is back"
