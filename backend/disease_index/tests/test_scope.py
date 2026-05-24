"""Editorial scope policy is the gate between the autocomplete and the
``Run research`` button. These tests pin the table down so the wrong
category never sneaks past the UI guard.
"""

from __future__ import annotations

import pytest

from backend.disease_index.models import DiseaseCategory
from backend.disease_index.scope import is_hard_blocked, is_in_scope, scope_label


@pytest.mark.parametrize("category", ["genetic", "predominantly_genetic"])
def test_genetic_categories_are_in_scope(category: DiseaseCategory) -> None:
    assert is_in_scope(category) is True
    assert is_hard_blocked(category) is False


@pytest.mark.parametrize("category", ["infectious", "acquired"])
def test_infectious_and_acquired_are_hard_blocked(category: DiseaseCategory) -> None:
    assert is_in_scope(category) is False
    assert is_hard_blocked(category) is True


def test_multifactorial_is_soft_warning_only() -> None:
    assert is_in_scope("multifactorial") is False
    # Hard-block is False — the user can still click through with a warning.
    assert is_hard_blocked("multifactorial") is False


def test_unknown_category_is_unblocked_but_out_of_scope() -> None:
    assert is_in_scope("unknown") is False
    assert is_hard_blocked("unknown") is False


def test_none_category_defaults_to_in_scope() -> None:
    """Unclassified Orphanet imports remain searchable until classification fills in."""
    assert is_in_scope(None) is True
    assert is_hard_blocked(None) is False


def test_scope_label_is_user_friendly() -> None:
    assert scope_label("genetic") == "Genetic"
    assert scope_label("infectious").startswith("Infectious")
    assert scope_label(None) == "Unclassified"
