"""Merge seed specialists with doctor_finder hits (same slug / name)."""
from __future__ import annotations

from backend.doctor_catalog import clear_finder_docs_index, get_doctors_for_disease


def _finder_hit_dowgierd() -> list[dict]:
    return [
        {
            "slug": "dowgierd",
            "name": "Prof. Krzysztof Dowgierd",
            "specialty": "Oral and maxillofacial surgery",
            "role": "National consultant",
            "institution": "WSSD Olsztyn · updated affiliation from PubMed workflow",
            "city": "Olsztyn",
            "country": "PL",
            "lat": 53.778,
            "lng": 20.48,
            "diseases": ["fd"],
            "pubmedRole": "research_participant",
            "score": 92,
            "evidence": {
                "firstOrLastAuthorPapers": 20,
                "reviewPapers": 4,
                "citesRecentGuidelines": True,
                "activeLast2y": True,
                "guidelineOrConsensusCoauthor": True,
            },
            "publications": [
                {
                    "pmid": "99999999",
                    "title": "Workflow-only publication row",
                    "year": 2026,
                    "journal": "Test J",
                    "position": "author",
                }
            ],
            "bio": "This finder bio is intentionally longer than the seed stub so merge prefers it.",
            "publicSource": "PubMed · Doctor Finder",
            "endorsements": [],
            "contact": "form",
            "source": "doctor_finder",
            "executionId": "exec-merge-test-1",
        },
        {
            "slug": "only-from-workflow",
            "name": "Dr. Only From Workflow",
            "specialty": "Genetics",
            "role": "Clinician",
            "institution": "Example Hospital",
            "city": "Warsaw",
            "country": "PL",
            "lat": 52.229,
            "lng": 21.012,
            "diseases": ["fd"],
            "pubmedRole": "research_participant",
            "score": 40,
            "evidence": {
                "firstOrLastAuthorPapers": 2,
                "reviewPapers": 0,
                "citesRecentGuidelines": False,
                "activeLast2y": True,
                "guidelineOrConsensusCoauthor": False,
            },
            "publications": [],
            "bio": "New specialist from finder only.",
            "publicSource": "PubMed · Doctor Finder",
            "endorsements": [],
            "contact": "form",
            "source": "doctor_finder",
            "executionId": "exec-merge-test-2",
        },
    ]


def test_get_doctors_merges_seed_and_finder(monkeypatch) -> None:
    clear_finder_docs_index()
    monkeypatch.setattr(
        "backend.doctor_catalog._build_finder_docs_index",
        lambda: {"fd": _finder_hit_dowgierd()},
    )
    payload = get_doctors_for_disease("fd")
    assert payload["source"] == "merged"
    by_slug = {d["slug"]: d for d in payload["doctors"]}
    assert "only-from-workflow" in by_slug
    merged = by_slug["dowgierd"]
    assert merged["source"] == "merged"
    assert merged["score"] == 92
    assert merged["executionId"] == "exec-merge-test-1"
    assert merged["evidence"]["firstOrLastAuthorPapers"] >= 20
    assert merged["evidence"]["guidelineOrConsensusCoauthor"] is True
    pmids = {p["pmid"] for p in merged["publications"]}
    assert "99999999" in pmids
    assert "krzysztofdowgierd.pl" in merged["publicSource"] or "WSSD" in merged["publicSource"]
    # draft9 directory fields from the curated seed survive the merge (finder hit omits them).
    assert len(merged["practices"]) == 2
    assert len(merged["parentRecs"]) == 1
    assert merged["rodo"]["status"] == "published_optout"
    assert merged["experienceByDisease"]["mas"] == "research_participant"


def test_get_doctors_name_match_without_slug_overlap(monkeypatch) -> None:
    """Finder slug differs but normalized name matches seed — still merge."""

    def finder() -> list[dict]:
        row = _finder_hit_dowgierd()[0].copy()
        row["slug"] = "different-slug-from-model"
        return [row]

    clear_finder_docs_index()
    monkeypatch.setattr(
        "backend.doctor_catalog._build_finder_docs_index",
        lambda: {"fd": finder()},
    )
    payload = get_doctors_for_disease("fd")
    assert payload["source"] == "merged"
    merged = next(d for d in payload["doctors"] if d["slug"] == "dowgierd")
    assert merged["source"] == "merged"
    assert merged["score"] == 92
