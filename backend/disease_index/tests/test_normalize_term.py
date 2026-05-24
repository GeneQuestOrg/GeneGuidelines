"""``normalize_term`` is the single source of truth for query / alias keys.

Every assertion below is the same shape: a raw input the user might type
or an Orphanet alias might contain, mapped to the lower-cased,
ASCII-folded, space-separated form we store in ``alias_norm`` and search
against.
"""

from __future__ import annotations

import pytest

from backend.disease_index.repository import normalize_term


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Marfan syndrome", "marfan syndrome"),
        ("MARFAN", "marfan"),
        ("  Marfan  ", "marfan"),
        ("Marfan, FBN1", "marfan fbn1"),
        ("Zespół Marfana", "zespol marfana"),
        ("Choroba Fabry'ego", "choroba fabry ego"),
        ("OMIM:154700", "omim 154700"),
        ("ORPHA-558", "orpha 558"),
        ("Hutchinson-Gilford Progeria Syndrome", "hutchinson gilford progeria syndrome"),
        ("Niemann-Pick Disease", "niemann pick disease"),
        ("22q11.2 deletion", "22q11 2 deletion"),
        ("", ""),
        ("   ", ""),
        ("FBN1", "fbn1"),
    ],
)
def test_normalize_term_examples(raw: str, expected: str) -> None:
    assert normalize_term(raw) == expected


def test_diacritics_match_ascii_form() -> None:
    """A Polish-name search must hit the canonical row.

    The autocomplete is supposed to feel forgiving: a parent who types
    ``zespol marfana`` should land the Marfan suggestion just as someone
    who typed ``Marfan``. That only works if the alias was stored under
    its ASCII-folded form.
    """
    assert normalize_term("Zespół Marfana") == normalize_term("Zespol Marfana")
