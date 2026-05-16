from backend.flows.pubmed.pmid_scrubber import scrub_pmids


def test_scrub_pmids_removes_unverified_explicit_and_bare() -> None:
    text = "Valid PMID 31196103. Hallucinated PMID 12345678. Bare hallucinated 23456789."
    cleaned, removed = scrub_pmids(text, {"31196103"})

    assert "31196103" in cleaned
    assert "12345678" not in cleaned
    assert "23456789" not in cleaned
    assert cleaned.count("[PMID UNVERIFIED]") == 2
    assert removed == ["12345678", "23456789"]


def test_scrub_pmids_keeps_verified_bare_and_explicit() -> None:
    text = "PMID 31196103 supports this claim and 33276154 confirms it."
    cleaned, removed = scrub_pmids(text, {"31196103", "33276154"})

    assert cleaned == text
    assert removed == []


def test_scrub_pmids_tracks_removed_only_once() -> None:
    text = "PMID 12345678 appears twice: PMID 12345678 and bare 12345678."
    cleaned, removed = scrub_pmids(text, set())

    assert cleaned.count("[PMID UNVERIFIED]") == 3
    assert removed == ["12345678"]
