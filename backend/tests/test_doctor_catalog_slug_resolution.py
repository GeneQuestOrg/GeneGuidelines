"""Resolve doctor_finder disease_name → catalog slug for API / persistence."""
from __future__ import annotations

import pytest

from backend.content_db import ensure_content_schema, seed_content_if_empty
from backend.database import init_db
from backend.doctor_catalog import catalog_slug_for_finder_input


@pytest.fixture(autouse=True)
def _init_catalog_db() -> None:
    init_db()
    ensure_content_schema()
    seed_content_if_empty()


def test_catalog_slug_from_full_disease_title() -> None:
    assert catalog_slug_for_finder_input("Fibrous Dysplasia") == "fd"


def test_catalog_slug_from_slug_token() -> None:
    assert catalog_slug_for_finder_input("Experts for fd in EU") == "fd"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("McCune-Albright spectrum", "mas"),
        ("Noonan spectrum disorder", "noonan"),
    ],
)
def test_catalog_slug_keyword_shortcuts(text: str, expected: str) -> None:
    assert catalog_slug_for_finder_input(text) == expected
