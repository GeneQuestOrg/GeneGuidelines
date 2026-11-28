"""The trials seed must not invent studies or people.

On 2026-11-28 production was found serving two seeded trials that ClinicalTrials.gov does not know, each with a named investigator and a made-up contact address, shown to parents as recruiting. The registry cannot be asked from a test, so this pins what can be checked offline: the two identifiers are gone for good, and a seeded trial never names a person or a contact address (the real ones come from the registry record through the trials finder).
"""

from __future__ import annotations

import json
from pathlib import Path

SEED = Path(__file__).resolve().parents[1] / "content_trials_seed.json"
FABRICATED = {"NCT05998877", "NCT06334455"}


def _trials() -> list[dict]:
    return json.loads(SEED.read_text(encoding="utf-8"))["trials"]


def test_the_two_invented_trials_are_not_seeded():
    assert FABRICATED.isdisjoint({t["nct"] for t in _trials()})


def test_a_seeded_trial_names_no_person_and_no_contact_address():
    for trial in _trials():
        assert not (trial.get("principalInvestigator") or "").strip(), trial["nct"]
        assert not (trial.get("contact") or "").strip(), trial["nct"]


def test_the_migration_deletes_exactly_the_invented_trials():
    import importlib.util

    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "d7e1a4c9b2f6_delete_fabricated_trials.py"
    spec = importlib.util.spec_from_file_location("delete_fabricated_trials", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.FABRICATED_NCTS) == FABRICATED
