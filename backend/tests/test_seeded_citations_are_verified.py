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
    # Riminucci M (last, 18/18) and Hsiao EC (17/18) both authored this 2025 review;
    # it also sits on the FD shelf, so the citation and the guideline agree.
    "40781626": (
        "Fibrous dysplasia/McCune-Albright syndrome: state-of-the-art advances, "
        "pathogenesis, and basic/translational research."
    ),
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


def test_no_seeded_record_carries_unmeasured_evidence_metrics() -> None:
    """Invented figures about real people are the same defect as invented citations.

    The seeded records used to declare things like firstOrLastAuthorPapers: 19 and
    reviewPapers: 4 for a named scientist — numbers nobody counted, rendered on the
    profile under "First / last author papers" as measured fact. Zeroing them would
    have been just as false, so the field is optional now and a hand-written record
    simply omits it. Measured evidence still arrives from the doctor-finder pipeline,
    which counts what it actually saw.
    """
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    rows = data.get("doctors", data) if isinstance(data, dict) else data

    with_evidence = [str(doc.get("slug", "?")) for doc in rows if "evidence" in doc]

    assert not with_evidence, (
        f"these seeded records claim measured evidence: {with_evidence}. "
        "Seed data is hand-written, so the numbers cannot have been measured — "
        "omit the block and let the pipeline supply it."
    )


def test_an_unmeasured_doctor_gets_no_evidence_block_rather_than_zeros() -> None:
    """Zeros are a finding; absence is the truth when nobody counted.

    The merge used to synthesise a full block from two empty inputs, so stripping the
    invented numbers out of the seed would have quietly reintroduced them as
    "First / last author papers: 0" on every hand-written profile.
    """
    from backend.doctor_catalog import _merge_evidence_dicts

    assert _merge_evidence_dicts({}, {}) is None

    measured = _merge_evidence_dicts({}, {"firstOrLastAuthorPapers": 7})
    assert measured is not None and measured["firstOrLastAuthorPapers"] == 7


def test_a_doctor_without_publications_carries_no_research_role() -> None:
    """PubMed roles describe a publication record. Applied to someone with none they
    are simply false — and the person it hit hardest was the surgeon a family most
    needs to find, shown as a "research leader" with zero papers. Their standing is
    real, it just is not of this kind, so it is carried by the clinical signals
    (official post, patient-organisation endorsement) instead.
    """
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    rows = data.get("doctors", data) if isinstance(data, dict) else data

    offenders = [
        f"{doc.get('slug')}: pubmedRole={doc.get('pubmedRole')} with 0 publications"
        for doc in rows
        if not (doc.get("publications") or [])
        and str(doc.get("pubmedRole", "unknown")) != "unknown"
    ]

    assert not offenders, "\n  ".join(["research roles without a record:", *offenders])


def test_seeded_records_do_not_claim_pubmed_provenance() -> None:
    """They were curated by hand; addedVia="pubmed" claimed they were discovered by
    the pipeline, which is a provenance label nobody could check."""
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    rows = data.get("doctors", data) if isinstance(data, dict) else data

    wrong = [doc.get("slug") for doc in rows if doc.get("addedVia") == "pubmed"]

    assert not wrong, f"seeded records claiming PubMed discovery: {wrong}"
