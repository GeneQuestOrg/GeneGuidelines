"""The generator's worked example is the hand-written FD block, word for word: backend/guidelines/points/fd_worked_example.json must match askP/askQ/askS 1-6 in the public site's locale files."""

from __future__ import annotations

import json
from pathlib import Path

from backend.guidelines.points.prompts import worked_example

LOCALES = Path(__file__).resolve().parents[2] / "frontend-public" / "src" / "locales"


def _ask(locale: str) -> dict[str, str]:
    found: dict[str, str] = {}

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str) and key.startswith("ask"):
                    found[key] = value
                else:
                    walk(value)

    walk(json.loads((LOCALES / locale / "disease-map.json").read_text(encoding="utf-8")))
    return found


def test_worked_example_is_the_hand_written_fd_block():
    en, pl = _ask("en"), _ask("pl")
    points = worked_example()["points"]
    assert len(points) == 6
    for n, p in enumerate(points, 1):
        assert p == {"quote": en[f"askS{n}"], "summary_en": en[f"askP{n}"], "summary_pl": pl[f"askP{n}"], "question_en": en[f"askQ{n}"], "question_pl": pl[f"askQ{n}"]}
