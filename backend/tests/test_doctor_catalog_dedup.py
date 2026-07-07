"""Dedup of the same real person split across PubMed author clusters (no DB).

PubMed disambiguation fragments one person into several author_key clusters, which surfaced
flagship experts (Hsiao, Appelman-Dijkstra) and others (Collins, Boyce) two or three times in the
public directory. _dedup_finder_docs collapses them; the seed↔finder loose-name match merges a
curated seed row with its middle-initial finder variant.
"""
from __future__ import annotations

from backend.doctor_catalog import (
    _dedup_finder_docs,
    _finder_index_matching_seed,
    _loose_name_key,
)


def _row(slug: str, name: str, country: str = "US", score: int = 5, **extra) -> dict:
    return {"slug": slug, "name": name, "country": country, "score": score,
            "diseases": ["fd"], "pubmedRole": "unknown", **extra}


def test_loose_name_key_collapses_middle_initial() -> None:
    assert _loose_name_key("Edward Hsiao") == _loose_name_key("Edward C Hsiao")
    assert _loose_name_key("Edward C. Hsiao") == "edward hsiao"
    # Single-token names never loose-match (too collision-prone).
    assert _loose_name_key("Collins") == ""


def test_dedup_collapses_same_name_same_country() -> None:
    rows = [
        _row("m-t-collins", "Michael T Collins", score=64),
        _row("michael-collins", "Michael Collins", score=40),
    ]
    out = _dedup_finder_docs(rows)
    assert len(out) == 1
    # The merge keeps the higher score.
    assert out[0]["score"] == 64


def test_dedup_keeps_same_surname_different_country_separate() -> None:
    # Two different people who happen to share a surname must NOT be fused.
    rows = [
        _row("j-smith-us", "John Smith", country="US"),
        _row("j-smith-gb", "John Smith", country="GB"),
    ]
    out = _dedup_finder_docs(rows)
    assert len(out) == 2


def test_dedup_merges_identical_slug_regardless_of_country() -> None:
    rows = [
        _row("orcid:0000-0001", "Alison Boyce", country="US", score=64),
        _row("orcid:0000-0001", "Alison M Boyce", country="", score=10),
    ]
    out = _dedup_finder_docs(rows)
    assert len(out) == 1


def test_seed_matches_finder_middle_initial_variant() -> None:
    # The regression: curated "Edward Hsiao" seed must merge with finder "Edward C Hsiao".
    seed = _row("hsiao", "Dr. Edward Hsiao")
    finder = [_row("edward-c-hsiao", "Edward C Hsiao")]
    assert _finder_index_matching_seed(seed, finder, set()) == 0
