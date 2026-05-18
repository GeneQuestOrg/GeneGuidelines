"""Tests for parent care pathway JSON validation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.parent_pathway_schema import (
    ParentPathwayValidationError,
    coerce_pathway_tree_object,
    validate_parent_pathway_tree,
)
from backend.tests.parent_pathway_fixtures import ABOUT_SUMMARY_MIN, three_action_steps


def _load_fd_seed_tree() -> dict:
    path = Path(__file__).resolve().parents[1] / "content_care_pathway_seed.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["fd"]


def test_validate_fd_seed_tree() -> None:
    tree, warnings = validate_parent_pathway_tree(_load_fd_seed_tree())
    assert tree["id"] == "root"
    assert 3 <= len(tree["children"]) <= 7
    assert "diagnosis" in tree["title"].lower() or "after" in tree["title"].lower()
    assert isinstance(warnings, list)


def test_coerce_root_wrapper() -> None:
    inner = _load_fd_seed_tree()
    wrapped = {"root": inner}
    coerced = coerce_pathway_tree_object(wrapped)
    tree, _warnings = validate_parent_pathway_tree(coerced)
    assert tree["id"] == "root"
    assert len(tree["children"]) >= 3


def test_schema_error_includes_field_hint() -> None:
    tree = {
        "id": "root",
        "title": "Test",
        "children": [],
    }
    with pytest.raises(ParentPathwayValidationError, match="about"):
        validate_parent_pathway_tree(tree)


def test_requires_about_on_root() -> None:
    tree = {
        "id": "root",
        "title": "Root",
        "children": [
            {
                "id": "a1",
                "action": True,
                "title": "Organize referral paperwork before your visit",
                "specialty": "Pediatrics",
                "questions": ["What should we ask at the visit?"],
            }
        ],
    }
    with pytest.raises(ParentPathwayValidationError, match="about"):
        validate_parent_pathway_tree(tree)


def test_rejects_placeholder_single_action_step() -> None:
    tree = {
        "id": "root",
        "title": "API publish pathway test",
        "subtitle": "Short subtitle for families after diagnosis.",
        "about": {
            "title": "What is this condition?",
            "summary": ABOUT_SUMMARY_MIN,
        },
        "children": [
            {
                "id": "step-1",
                "action": True,
                "title": "First step",
                "specialty": "Your GP",
                "whatToExpect": (
                    "You will talk with your care team about what already happened, what papers you have, "
                    "and what the next safe steps are. Expect plain language — bring a notepad or use your phone."
                ),
                "questions": [
                    "What should we do first?",
                    "Who can we call if we are worried before the next visit?",
                ],
                "citations": [],
                "evidenceGap": True,
            }
        ],
    }
    with pytest.raises(ParentPathwayValidationError, match="at least 3"):
        validate_parent_pathway_tree(tree)


def test_rejects_copy_paste_three_steps() -> None:
    """Same boilerplate on every line must not pass as a patient chart."""
    shared = (
        "Your team explains what will happen at this visit, how long it may take, and how results reach you. "
        "Bring your list of questions; it is normal to feel overwhelmed."
    )
    tree = {
        "id": "root",
        "title": "After diagnosis — your next visits",
        "subtitle": "Plain-language checklist.",
        "about": {"title": "What this means", "summary": ABOUT_SUMMARY_MIN},
        "children": [
            {
                "id": f"step-{i}",
                "action": True,
                "title": f"Concrete step {i} after diagnosis",
                "specialty": "Your coordinating clinician",
                "whatToExpect": shared,
                "questions": [
                    "What should we bring to this visit?",
                    "Who can we call if symptoms change before the next appointment?",
                ],
                "citations": ["31196103"],
                "evidenceGap": False,
            }
            for i in (1, 2, 3)
        ],
    }
    with pytest.raises(ParentPathwayValidationError, match="repeat"):
        validate_parent_pathway_tree(tree)


def test_rejects_hollow_concrete_step_title() -> None:
    wt = (
        "You meet a nurse who checks height, weight, and any new symptoms since your last letter. "
        "They tell you what happens next in the visit."
    )
    tree = {
        "id": "root",
        "title": "Next visits",
        "subtitle": "One week at a time.",
        "about": {"title": "What this means", "summary": ABOUT_SUMMARY_MIN},
        "children": [
            {
                "id": "bad-title",
                "action": True,
                "title": "Concrete step 1 after diagnosis",
                "specialty": "GP",
                "whatToExpect": wt,
                "questions": ["What papers help you most?", "Can we bring a relative?"],
                "citations": ["31196103"],
                "evidenceGap": False,
            },
            {
                "id": "ok-2",
                "action": True,
                "title": "Genetics explains the blood test plan",
                "specialty": "Clinical genetics",
                "whatToExpect": wt.replace("nurse", "genetic counsellor").replace("height", "family tree"),
                "questions": ["How long until results?", "Who phones us?"],
                "citations": ["31196103"],
                "evidenceGap": False,
            },
            {
                "id": "ok-3",
                "action": True,
                "title": "Orthopedics reviews bone pain and activity",
                "specialty": "Orthopedic clinic",
                "whatToExpect": wt.replace("nurse", "surgeon").replace("height", "pain diary"),
                "questions": ["What sports are safe now?", "When is the next scan?"],
                "citations": ["31196103"],
                "evidenceGap": False,
            },
        ],
    }
    with pytest.raises(ParentPathwayValidationError, match="placeholder"):
        validate_parent_pathway_tree(tree)


def test_rejects_deep_nesting() -> None:
    deep = {
        "id": "root",
        "title": "Test",
        "about": {
            "title": "About the condition",
            "summary": ABOUT_SUMMARY_MIN,
        },
        "children": [
            {
                "id": "l1",
                "title": "L1?",
                "branches": [
                    {
                        "answer": "Yes",
                        "next": {
                            "id": "l2",
                            "title": "L2?",
                            "branches": [
                                {
                                    "answer": "Yes",
                                    "next": {
                                        "id": "l3",
                                        "title": "L3?",
                                        "branches": [
                                            {
                                                "answer": "Yes",
                                                "next": {
                                                    "id": "l4",
                                                    "title": "L4?",
                                                    "branches": [
                                                        {
                                                            "answer": "Yes",
                                                            "next": {
                                                                "id": "l5",
                                                                "title": "L5?",
                                                                "branches": [
                                                                    {
                                                                        "answer": "Yes",
                                                                        "next": {
                                                                            "id": "l6",
                                                                            "title": "L6?",
                                                                            "branches": [
                                                                                {
                                                                                    "answer": "Yes",
                                                                                    "next": {
                                                                                        "id": "act",
                                                                                        "action": True,
                                                                                        "title": "Act",
                                                                                        "specialty": "MD",
                                                                                        "questions": ["Q?"],
                                                                                    },
                                                                                }
                                                                            ],
                                                                        },
                                                                    }
                                                                ],
                                                            },
                                                        }
                                                    ],
                                                },
                                            }
                                        ],
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    with pytest.raises(ParentPathwayValidationError, match="max depth"):
        validate_parent_pathway_tree(deep)


def test_pmid_must_be_in_guideline_when_allowed_set() -> None:
    tree = {
        "id": "root",
        "title": "Root",
        "subtitle": "Plain-language next steps after diagnosis — your team is here to help.",
        "about": {
            "title": "What this means",
            "summary": ABOUT_SUMMARY_MIN,
        },
        "children": three_action_steps(bad_pmid_step=3),
    }
    with pytest.raises(ParentPathwayValidationError, match="99999999"):
        validate_parent_pathway_tree(tree, allowed_pmids={"31196103"})
