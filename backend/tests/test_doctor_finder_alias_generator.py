from __future__ import annotations

from backend.flows.doctor_finder.alias_generator import merge_alias_lists


def test_merge_alias_lists_preserves_manual_order_and_dedupes() -> None:
    assert merge_alias_lists(["a", "B"], ["b", "a", "B"]) == ["a", "B"]


def test_merge_alias_lists_appends_generated() -> None:
    assert merge_alias_lists(["FD"], ["McCune-Albright", "MAS"]) == ["FD", "McCune-Albright", "MAS"]
