from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from backend.flows.doctor_finder.scoring import (
    FLAG_BONUSES,
    MAX_FLAG_BONUS,
    RECENCY_BONUS_PER_PAPER,
    compute_raw,
    normalize,
    run,
)

NOW = date(2026, 1, 1)


def _author(role: str, flags: dict | None = None, papers: list | None = None, **counts: Any) -> dict:
    return {
        "author_key": "test",
        "role": {"role": role, "justification": ""},
        "flags": flags or {
            "guideline_author": False,
            "active_last_2y": False,
            "runs_clinical_trial": False,
            "international_collab": False,
            "cites_current_guidelines": False,
        },
        "papers": papers or [],
        "guideline_count": 0,
        "review_count": 0,
        "original_count": 0,
        "case_report_count": 0,
        "paper_count": 0,
        "score": 0.0,
        **counts,
    }


def test_guideline_author_higher_than_peripheral() -> None:
    guideline = _author("guideline_author")
    peripheral = _author("peripheral")
    assert compute_raw(guideline, NOW) > compute_raw(peripheral, NOW)


def test_first_author_position_higher_than_middle() -> None:
    first_paper = [{"author_position": "first", "year": 2020}]
    middle_paper = [{"author_position": "middle", "year": 2020}]
    author_first = _author("active_contributor", papers=first_paper)
    author_middle = _author("active_contributor", papers=middle_paper)
    assert compute_raw(author_first, NOW) > compute_raw(author_middle, NOW)


def test_recency_bonus_for_recent_paper() -> None:
    recent_paper = [{"author_position": "middle", "year": NOW.year - 1}]
    old_paper = [{"author_position": "middle", "year": NOW.year - 5}]
    author_recent = _author("active_contributor", papers=recent_paper)
    author_old = _author("active_contributor", papers=old_paper)
    diff = compute_raw(author_recent, NOW) - compute_raw(author_old, NOW)
    assert diff == pytest.approx(RECENCY_BONUS_PER_PAPER)


def test_flag_bonus_capped_at_max() -> None:
    all_flags = {
        "guideline_author": True,
        "active_last_2y": True,
        "runs_clinical_trial": True,
        "international_collab": True,
        "cites_current_guidelines": True,
    }
    total_flags = sum(FLAG_BONUSES.values())
    assert total_flags > MAX_FLAG_BONUS, "test precondition: all flags must exceed cap"

    author = _author("active_contributor", flags=all_flags)
    no_flag_author = _author("active_contributor")
    diff = compute_raw(author, NOW) - compute_raw(no_flag_author, NOW)
    assert diff == pytest.approx(MAX_FLAG_BONUS)


def test_single_author_normalized_to_100() -> None:
    author = _author("active_contributor", papers=[{"author_position": "first", "year": 2025}])
    with_raw = [{**author, "score": compute_raw(author, NOW)}]
    result = normalize(with_raw)
    assert result[0]["score"] == pytest.approx(100.0)


def test_two_authors_higher_raw_gets_higher_normalized() -> None:
    high = _author("guideline_author", papers=[{"author_position": "first", "year": 2025}])
    low = _author("peripheral")
    with_raw = [
        {**high, "score": compute_raw(high, NOW)},
        {**low, "score": compute_raw(low, NOW)},
    ]
    result = normalize(with_raw)
    assert result[0]["score"] > result[1]["score"]


def test_equal_raw_scores_all_normalized_to_100() -> None:
    authors = [_author("peripheral"), _author("peripheral")]
    with_raw = [{**a, "score": compute_raw(a, NOW)} for a in authors]
    result = normalize(with_raw)
    for a in result:
        assert a["score"] == pytest.approx(100.0)


def test_normalize_empty_list() -> None:
    assert normalize([]) == []


def test_run_empty_authors_does_not_raise() -> None:
    result = run({"aggregated_authors": [], "query": "noonan"}, now=NOW)
    assert result["aggregated_authors"] == []
    assert result["query"] == "noonan"


def test_run_returns_context_with_float_scores() -> None:
    authors = [
        _author("guideline_author"),
        _author("active_contributor"),
        _author("peripheral"),
    ]
    context = {"aggregated_authors": authors, "query": "test"}
    result = run(context, now=NOW)

    assert "aggregated_authors" in result
    assert result["query"] == "test"
    for a in result["aggregated_authors"]:
        assert isinstance(a["score"], float)
