"""pm-1 deterministic retrieval toggle."""
from __future__ import annotations

from backend.config import PUBMED_PM1_DETERMINISTIC_RETRIEVAL


def test_pubmed_pm1_deterministic_retrieval_default_on() -> None:
    assert PUBMED_PM1_DETERMINISTIC_RETRIEVAL is True
