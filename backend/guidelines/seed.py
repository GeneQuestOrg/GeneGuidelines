"""Idempotent seed for the guidelines layer.

Loads ``backend/seed_guidelines.json`` (mirrors the frontend fixtures) the first
time the synthesis table is empty, so a fresh DB serves the same FD/MAS data the
fixture mode does. Best-effort at startup — never blocks boot.
"""

from __future__ import annotations

import json
from pathlib import Path

from .repository import SqlaGuidelinesRepo

_SEED_PATH = Path(__file__).resolve().parent.parent / "seed_guidelines.json"


def load_seed_payload() -> dict:
    return json.loads(_SEED_PATH.read_text(encoding="utf-8"))


def seed_guidelines(repo: SqlaGuidelinesRepo, payload: dict) -> None:
    """Insert every disease's shelf / synthesis / suggestions / signals."""
    for slug, disease in payload.items():
        if slug.startswith("_") or not isinstance(disease, dict):
            continue  # skip the "_note" metadata key
        for order, doc in enumerate(disease.get("sourceDocuments", [])):
            repo.insert_source_document(slug, doc, order)
        synthesis = disease.get("synthesis")
        if synthesis:
            repo.upsert_synthesis(slug, synthesis)
        for order, suggestion in enumerate(disease.get("suggestions", [])):
            repo.insert_suggestion(slug, suggestion, order)
        for section_id, signal in disease.get("signals", {}).items():
            repo.upsert_synthesis_signal(slug, section_id, signal)


def seed_guidelines_if_empty(repo: SqlaGuidelinesRepo | None = None) -> bool:
    """Seed only when the synthesis table is empty. Returns True if it seeded."""
    repo = repo or SqlaGuidelinesRepo()
    if repo.has_any_synthesis():
        return False
    seed_guidelines(repo, load_seed_payload())
    return True


__all__ = ["load_seed_payload", "seed_guidelines", "seed_guidelines_if_empty"]
