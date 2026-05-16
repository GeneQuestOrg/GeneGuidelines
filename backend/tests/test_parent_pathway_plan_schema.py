"""Preset schema for parent_pathway pp-plan (simple LLM step)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.agents.schemas import ParentPathwayPlanOutput, resolve_simple_result_model


def _valid_payload() -> dict:
    return {
        "family_headline": "You are not alone — here is a clear first path after this diagnosis.",
        "evidence_hotspots": [
            "Confirming the diagnosis with targeted testing",
            "Bone health and growth monitoring when the guideline mentions skeletal care",
        ],
        "priority_actions": [
            "Ask your GP for a referral to clinical genetics within the next few weeks.",
            "Request copies of imaging and lab results to bring to the first specialist visit.",
            "Write down daily symptoms and questions to share at appointments.",
        ],
        "emotional_and_logistics_notes": (
            "Families often feel rushed and forget questions; offer short sentences, "
            "interpreter access, and practical help with school letters or time off work."
        ),
        "sensitivity_flags": ["growth and puberty concerns"],
        "synthesis_directives": (
            "Map each priority_actions line to one checklist step with a distinct whatToExpect; "
            "do not merge genetics and orthopedics; omit topics absent from the evidence bundle."
        ),
    }


def test_parent_pathway_plan_output_ok() -> None:
    m = ParentPathwayPlanOutput.model_validate(_valid_payload())
    assert len(m.priority_actions) == 3
    assert m.sensitivity_flags


def test_parent_pathway_plan_duplicate_priority_rejected() -> None:
    p = _valid_payload()
    p["priority_actions"] = [
        "Book genetics to discuss results and next steps with your care team.",
        "Book genetics to discuss results and next steps with your care team.",
        "Ask for referral paperwork from your GP clinic this week.",
    ]
    with pytest.raises(ValidationError):
        ParentPathwayPlanOutput.model_validate(p)


def test_parent_pathway_plan_resolve_simple_model() -> None:
    node = {"output_schema_key": "parent_pathway_plan", "output_schema": None}
    model, err = resolve_simple_result_model(node)
    assert err is None
    assert model is ParentPathwayPlanOutput
