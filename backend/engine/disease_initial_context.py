"""Merge per-disease fields into flow initial_context."""
from __future__ import annotations

from typing import Any


def merge_disease_into_initial_context(store: dict[str, Any]) -> None:
    """Apply store['disease_initial'] onto store['initial_context'] when present."""
    disease_fields = store.get("disease_initial")
    if not isinstance(disease_fields, dict) or not disease_fields:
        return
    initial = store.setdefault("initial_context", {})
    if not isinstance(initial, dict):
        return
    initial.update(disease_fields)
