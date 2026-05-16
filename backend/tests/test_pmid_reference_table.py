import pytest
from backend.flows.pubmed.pmid_reference_table import build_reference_table, _first_author_surname


def test_empty_articles_returns_placeholder():
    assert build_reference_table([]) == "(no verified PMIDs available)"


def test_basic_article():
    arts = [{"pmid": "31196103", "authors": ["Javaid, Muhammad"], "year": "2019",
              "journal": "Orphanet J Rare Dis", "title": "Best practice management guidelines"}]
    result = build_reference_table(arts)
    assert "31196103" in result
    assert "Javaid" in result
    assert "2019" in result


def test_deduplication():
    arts = [
        {"pmid": "12345678", "title": "First"},
        {"pmid": "12345678", "title": "Duplicate"},
    ]
    result = build_reference_table(arts)
    assert result.count("12345678") == 1


def test_title_truncation():
    long_title = "A" * 100
    arts = [{"pmid": "12345678", "title": long_title}]
    result = build_reference_table(arts)
    assert "…" in result


def test_first_author_surname_list():
    assert _first_author_surname(["Smith, John"]) == "Smith"
    assert _first_author_surname(["Smith J"]) == "Smith"
    assert _first_author_surname([]) == "Unknown"


def test_first_author_surname_string():
    assert _first_author_surname("Javaid, Muhammad") == "Javaid"


def test_max_entries_limit():
    arts = [{"pmid": str(i + 1000000), "title": f"Article {i}"} for i in range(300)]
    result = build_reference_table(arts)
    # 200 data lines × 3 pipes + 3 pipes in the header format line = 603 max
    assert result.count("|") <= 200 * 3 + 3  # 200 lines × 3 pipes + header pipes
