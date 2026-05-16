"""Word-boundary truncation for PubMed author-fetch abstracts."""

from __future__ import annotations

from backend.tools.pubmed_runtime import (
    PUBMED_AUTHOR_XML_ABSTRACT_MAX_CHARS,
    truncate_text_on_word_boundary,
)


def test_truncate_noop_when_short() -> None:
    s = "short abstract"
    assert truncate_text_on_word_boundary(s, 100) == s


def test_truncate_prefers_last_space() -> None:
    s = "alpha " + "beta " * 100
    out = truncate_text_on_word_boundary(s, 20)
    assert len(out) <= 20
    assert out == "alpha beta beta"
    assert not out.endswith(" ")


def test_truncate_no_space_falls_back_to_hard_cap() -> None:
    long_token = "x" * (PUBMED_AUTHOR_XML_ABSTRACT_MAX_CHARS + 50)
    out = truncate_text_on_word_boundary(long_token, PUBMED_AUTHOR_XML_ABSTRACT_MAX_CHARS)
    assert len(out) == PUBMED_AUTHOR_XML_ABSTRACT_MAX_CHARS
