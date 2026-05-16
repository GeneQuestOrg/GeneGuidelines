from __future__ import annotations

from backend.flows.doctor_finder.report_builder import run


def _make_author(
    key: str,
    last_name: str,
    fore_name: str,
    country: str,
    score: float,
) -> dict:
    """Build a minimal AggregatedAuthor dict for testing."""
    return {
        "author_key": key,
        "last_name": last_name,
        "fore_name": fore_name,
        "initials": fore_name[:1] if fore_name else "",
        "country_primary": country,
        "continent_primary": "Europe" if country in ("IT", "NL") else "North America",
        "institution_primary": f"University of {last_name}",
        "role": {"role": "senior_investigator", "justification": "many papers"},
        "flags": {
            "guideline_author": False,
            "cites_current_guidelines": False,
            "active_last_2y": True,
            "runs_clinical_trial": False,
            "international_collab": False,
        },
        "score": score,
        "papers": [
            {
                "pmid": f"1000{i}",
                "title": f"Paper {i} by {last_name}",
                "year": 2022 + i,
                "publication_types": ["Journal Article"],
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/1000{i}/",
                "author_position": "first",
            }
            for i in range(3)
        ],
        "guideline_count": 0,
        "review_count": 1,
        "case_report_count": 0,
        "original_count": 2,
        "paper_count": 3,
        "ai_justification": None,
    }


AUTHORS = [
    _make_author("rossi_m", "Rossi", "Marco", "IT", 90.0),
    _make_author("ferrari_l", "Ferrari", "Luca", "IT", 80.0),
    _make_author("smith_j", "Smith", "John", "US", 70.0),
    _make_author("johnson_a", "Johnson", "Amy", "US", 60.0),
    _make_author("dejong_k", "DeJong", "Karen", "NL", 50.0),
]

BASE_CONTEXT = {
    "aggregated_authors": AUTHORS,
    "query_text": "Marfan syndrome[MeSH]",
    "total_papers_scanned": 250,
    "initial": {
        "disease_name": "Marfan Syndrome",
        "top_n_authors": 20,
    },
}


def test_continent_filter_keeps_only_matching_continent() -> None:
    ctx = {
        **BASE_CONTEXT,
        "initial": {
            **BASE_CONTEXT["initial"],
            "continent": "Europe",
        },
    }
    result = run(ctx)
    countries = {a["country"] for a in result["doctor_report"]["top_authors"]}
    assert "US" not in countries
    assert "IT" in countries or "NL" in countries
    assert "Europe" in result["doctor_report"]["markdown"]


def test_continent_filter_empty_when_resolved_but_no_match() -> None:
    """Europe filter vs US-only authors: strict empty list (no silent unfiltered non‑Europeans)."""
    us_only = [a for a in AUTHORS if a.get("country_primary") == "US"]
    ctx = {
        "aggregated_authors": us_only,
        "query_text": "q",
        "total_papers_scanned": 2,
        "initial": {
            "disease_name": "Test",
            "top_n_authors": 20,
            "continent": "Europe",
        },
    }
    result = run(ctx)
    assert result["doctor_report"]["top_authors"] == []
    md = result["doctor_report"]["markdown"]
    assert "no ranked authors" in md.lower()


def test_continent_filter_prefers_country_iso_over_wrong_continent_primary() -> None:
    """Majority country US must not be overridden by a wrong continent_primary for filtering."""
    us_wrong = _make_author("hsiao_e", "Hsiao", "Edward", "US", 100.0)
    us_wrong["continent_primary"] = "Europe"
    ctx = {
        "aggregated_authors": [us_wrong],
        "query_text": "q",
        "total_papers_scanned": 1,
        "initial": {
            "disease_name": "Test",
            "top_n_authors": 20,
            "continent": "Europe",
        },
    }
    result = run(ctx)
    assert result["doctor_report"]["top_authors"] == []


def test_continent_filter_uses_country_when_continent_primary_missing() -> None:
    """Resolve continent from ISO-2 when continent_primary is absent (PubMed-style gaps)."""
    de = _make_author("mueller_a", "Mueller", "Anna", "DE", 95.0)
    de["continent_primary"] = ""
    ctx = {
        "aggregated_authors": [de, _make_author("smith_j", "Smith", "John", "US", 70.0)],
        "query_text": "q",
        "total_papers_scanned": 2,
        "initial": {
            "disease_name": "Test",
            "top_n_authors": 20,
            "continent": "Europe",
        },
    }
    result = run(ctx)
    countries = {a["country"] for a in result["doctor_report"]["top_authors"]}
    assert "DE" in countries
    assert "US" not in countries


def test_continent_filter_empty_when_no_geography_resolved() -> None:
    """Sparse geography: filter is skipped so the ranked table is not blanked for every continent."""
    ghost = _make_author("ghost_x", "Ghost", "X", "", 99.0)
    ghost["country_primary"] = None
    ghost["continent_primary"] = None
    ctx = {
        "aggregated_authors": [ghost],
        "query_text": "q",
        "total_papers_scanned": 1,
        "initial": {
            "disease_name": "Test",
            "top_n_authors": 20,
            "continent": "Europe",
        },
    }
    result = run(ctx)
    assert len(result["doctor_report"]["top_authors"]) == 1
    md = result["doctor_report"]["markdown"]
    assert "not applied" in md.lower()


def test_continent_filter_skipped_when_resolved_fraction_below_threshold() -> None:
    """Below MIN_RESOLVED_CONTINENT_FRACTION, empty filter result → show unfiltered ranking + note."""
    us1 = _make_author("us_only", "Smith", "John", "US", 100.0)
    ghosts: list[dict] = []
    for i in range(19):
        g = _make_author(f"g{i}", f"Ghost{i}", "X", "", 90.0 - i)
        g["country_primary"] = None
        g["continent_primary"] = None
        ghosts.append(g)
    ctx = {
        "aggregated_authors": [us1, *ghosts],
        "query_text": "q",
        "total_papers_scanned": 20,
        "initial": {
            "disease_name": "Test",
            "top_n_authors": 20,
            "continent": "Europe",
        },
    }
    result = run(ctx)
    assert len(result["doctor_report"]["top_authors"]) == 20
    assert "not applied" in result["doctor_report"]["markdown"].lower()


def test_run_returns_doctor_report_key() -> None:
    result = run(BASE_CONTEXT)
    assert "doctor_report" in result


def test_top_authors_sorted_by_score_desc() -> None:
    result = run(BASE_CONTEXT)
    scores = [a["score"] for a in result["doctor_report"]["top_authors"]]
    assert scores == sorted(scores, reverse=True)


def test_first_author_rank_is_one() -> None:
    result = run(BASE_CONTEXT)
    assert result["doctor_report"]["top_authors"][0]["rank"] == 1


def test_total_authors_found_equals_input_count() -> None:
    result = run(BASE_CONTEXT)
    assert result["doctor_report"]["total_authors_found"] == 5


def test_markdown_contains_disease_name_and_table_header() -> None:
    result = run(BASE_CONTEXT)
    md = result["doctor_report"]["markdown"]
    assert "Marfan Syndrome" in md
    assert "| Rank |" in md


def test_top_n_authors_limits_entries() -> None:
    context = {
        **BASE_CONTEXT,
        "initial": {
            "disease_name": "Marfan Syndrome",
            "top_n_authors": 3,
        },
    }
    result = run(context)
    assert len(result["doctor_report"]["top_authors"]) == 3


def test_disease_name_passed_through_from_initial_context() -> None:
    context = {
        "aggregated_authors": AUTHORS,
        "query_text": "test",
        "total_papers_scanned": 10,
        "initial_context": {
            "disease_name": "Ehlers-Danlos Syndrome",
            "top_n_authors": 20,
        },
    }
    result = run(context)
    assert result["doctor_report"]["disease_name"] == "Ehlers-Danlos Syndrome"
