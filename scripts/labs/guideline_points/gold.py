"""The hand-written FD block (the calibration case) and the verifier's known-answer controls built from it.

The FD block lives in the public site's locale files (``askP1-6``, ``askQ1-6``, ``askS1-6`` in ``frontend-public/src/locales/{en,pl}/disease-map.json``) and was checked twice by an independent verifier against the full guideline, so its six points are the gold: the verifier should pass them. Each control in ``cases/verifier_controls.json`` takes one gold point and breaks it in one known way (modality, a dropped qualifier, a truncated quote, a presupposing or advising question, a Polish meaning change, an omission that changes the meaning); the verifier should return FIX on every one.
"""

from __future__ import annotations

import json

from backend.guidelines.points.models import DraftPoint

from .common import CASES_DIR, REPO_ROOT, LabError, sha256_file

LOCALES = {loc: REPO_ROOT / "frontend-public" / "src" / "locales" / loc / "disease-map.json" for loc in ("en", "pl")}
FD_GUIDELINE_DOC = "31196103"


def _ask(locale: str) -> dict:
    data = json.loads(LOCALES[locale].read_text(encoding="utf-8"))
    found: dict[str, str] = {}

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str) and key.startswith("ask"):
                    found[key] = value
                else:
                    walk(value)

    walk(data)
    return found


def gold_points() -> list[DraftPoint]:
    en, pl = _ask("en"), _ask("pl")
    points = []
    for n in range(1, 7):
        if f"askS{n}" not in en:
            raise LabError(f"askS{n} missing from {LOCALES['en']}")
        points.append(DraftPoint(
            id=f"gold{n}", doc_id=FD_GUIDELINE_DOC, section="", quote=en[f"askS{n}"], summary_en=en[f"askP{n}"], summary_pl=pl[f"askP{n}"],
            question_en=en[f"askQ{n}"], question_pl=pl[f"askQ{n}"], withdrawn=False, note="",
        ))
    return points


def gold_hashes() -> dict[str, str]:
    return {f"frontend-public/src/locales/{loc}/disease-map.json": sha256_file(path) for loc, path in LOCALES.items()}


def verifier_controls() -> list[dict]:
    """Every control as {id, base, expect, what, point}: the six gold points (PASS) and the corrupted variants (FIX)."""
    gold = {p.id: p for p in gold_points()}
    controls = [{"id": p.id, "base": p.id, "expect": "PASS", "what": "hand-written FD point, verified twice", "point": p} for p in gold.values()]
    spec = json.loads((CASES_DIR / "verifier_controls.json").read_text(encoding="utf-8"))
    for c in spec["controls"]:
        base = gold[c["base"]]
        controls.append({"id": c["id"], "base": c["base"], "expect": c["expect"], "what": c["what"], "point": base.model_copy(update={"id": c["id"], **c["change"]})})
    return controls
