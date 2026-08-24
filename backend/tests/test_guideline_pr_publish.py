"""Unit tests for the guideline PR publish merge.

These used to run against the seeded FD/MAS/Noonan documents and the
``content_pr_para_maps.json`` entries for PR-138/139/142. Those were AI-authored
change requests shipped as production content — including a paediatric denosumab
dosing schedule marked "verified by specialist network" — and were deleted, so
the merge is exercised here against synthetic documents instead. That is also the
better test: the three replace modes are what we care about, not the wording of
one seeded paragraph.
"""
from __future__ import annotations

import pytest

from backend.guideline_pr_publish import (
    GuidelinePrPublishError,
    apply_pr_to_guideline_document,
    publish_pr_to_stored_document,
)

_REVIEWER = "Dr. Test"


def _document(section_id: str, paragraphs: list[dict]) -> dict:
    return {"sections": [{"id": "other", "paragraphs": []}, {"id": section_id, "paragraphs": paragraphs}]}


def _section(document: dict, section_id: str) -> dict:
    return next(s for s in document["sections"] if s["id"] == section_id)


def test_replace_drops_removed_and_finalizes_added() -> None:
    """``replace``: the paragraph the PR removes goes, the one it adds is kept."""
    document = _document(
        "therapy",
        [
            {"id": "tx-keep", "text": "unchanged"},
            {"id": "tx-old", "text": "superseded", "prInDiff": {"prId": "PR-1", "removed": True}},
            {"id": "tx-new", "text": "replacement", "prInDiff": {"prId": "PR-1", "added": True}},
        ],
    )

    published = apply_pr_to_guideline_document(
        document,
        para_map={"targetSection": "therapy", "replaceMode": "replace", "targetParaIds": ["tx-new"]},
        pr_id="PR-1",
        reviewer=_REVIEWER,
    )

    paragraphs = _section(published, "therapy")["paragraphs"]
    assert [p["id"] for p in paragraphs] == ["tx-keep", "tx-new"]
    added = paragraphs[1]
    assert added.get("prInDiff") is None  # no longer "in a diff" once published
    assert added["lastChange"] == {
        "type": "verified",
        "by": _REVIEWER,
        "date": added["lastChange"]["date"],
        "prId": "PR-1",
    }
    # The source document is untouched — callers persist the returned copy.
    assert len(_section(document, "therapy")["paragraphs"]) == 3


def test_insert_after_adds_the_new_paragraph_behind_its_anchor() -> None:
    document = _document("cardiology", [{"id": "card-1", "text": "first"}, {"id": "card-2", "text": "second"}])

    published = apply_pr_to_guideline_document(
        document,
        para_map={
            "targetSection": "cardiology",
            "replaceMode": "insert-after",
            "insertAfter": "card-1",
            "addedParagraph": {"id": "card-echo", "text": "echo follow-up"},
        },
        pr_id="PR-2",
        reviewer=_REVIEWER,
    )

    paragraphs = _section(published, "cardiology")["paragraphs"]
    assert [p["id"] for p in paragraphs] == ["card-1", "card-echo", "card-2"]
    assert paragraphs[1]["lastChange"]["prId"] == "PR-2"


def test_insert_after_is_idempotent_when_the_paragraph_is_already_there() -> None:
    """Re-publishing must not duplicate the added paragraph."""
    document = _document(
        "cardiology",
        [{"id": "card-1", "text": "first"}, {"id": "card-echo", "text": "echo follow-up"}],
    )

    published = apply_pr_to_guideline_document(
        document,
        para_map={
            "targetSection": "cardiology",
            "replaceMode": "insert-after",
            "insertAfter": "card-1",
            "addedParagraph": {"id": "card-echo", "text": "echo follow-up"},
        },
        pr_id="PR-2",
        reviewer=_REVIEWER,
    )

    paragraphs = _section(published, "cardiology")["paragraphs"]
    assert [p["id"] for p in paragraphs] == ["card-1", "card-echo"]
    assert paragraphs[1]["lastChange"]["prId"] == "PR-2"


def test_already_applied_only_stamps_the_targeted_paragraphs() -> None:
    document = _document(
        "endocrine",
        [{"id": "endo-1", "text": "targeted"}, {"id": "endo-2", "text": "untouched"}],
    )

    published = apply_pr_to_guideline_document(
        document,
        para_map={
            "targetSection": "endocrine",
            "replaceMode": "already-applied",
            "targetParaIds": ["endo-1"],
        },
        pr_id="PR-3",
        reviewer=_REVIEWER,
    )

    paragraphs = _section(published, "endocrine")["paragraphs"]
    assert paragraphs[0]["lastChange"]["prId"] == "PR-3"
    assert "lastChange" not in paragraphs[1]


@pytest.mark.parametrize(
    ("para_map", "match"),
    [
        ({}, "paragraphMap"),
        ({"replaceMode": "replace", "targetParaIds": ["x"]}, "targetSection"),
        ({"targetSection": "nope", "replaceMode": "replace", "targetParaIds": ["x"]}, "not found"),
        (
            {
                "targetSection": "therapy",
                "replaceMode": "insert-after",
                "addedParagraph": {"id": "new"},
            },
            "insertAfter",
        ),
        (
            {
                "targetSection": "therapy",
                "replaceMode": "insert-after",
                "insertAfter": "missing-anchor",
                "addedParagraph": {"id": "new"},
            },
            "anchor paragraph",
        ),
    ],
)
def test_bad_paragraph_maps_refuse_to_publish(para_map: dict, match: str) -> None:
    """A half-specified map must fail loudly rather than silently reshape a guideline."""
    document = _document("therapy", [{"id": "tx-1", "text": "text"}])

    with pytest.raises(GuidelinePrPublishError, match=match):
        apply_pr_to_guideline_document(
            document, para_map=para_map, pr_id="PR-4", reviewer=_REVIEWER
        )


def test_replace_refuses_to_empty_a_section() -> None:
    document = _document(
        "therapy",
        [{"id": "tx-only", "text": "gone", "prInDiff": {"prId": "PR-5", "removed": True}}],
    )

    with pytest.raises(GuidelinePrPublishError, match="remove all paragraphs"):
        apply_pr_to_guideline_document(
            document,
            para_map={"targetSection": "therapy", "replaceMode": "replace", "targetParaIds": []},
            pr_id="PR-5",
            reviewer=_REVIEWER,
        )


def test_publish_from_store_raises_when_the_pr_has_no_paragraph_map() -> None:
    """The file-backed wrapper: no map on disk means no publish (nothing is seeded)."""
    with pytest.raises(GuidelinePrPublishError, match="paragraphMap"):
        publish_pr_to_stored_document(
            _document("therapy", [{"id": "tx-1", "text": "text"}]),
            pr_id="PR-999",
            reviewer=_REVIEWER,
        )
