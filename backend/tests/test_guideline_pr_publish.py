"""Unit tests for guideline PR publish merge."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.guideline_pr_publish import (
    GuidelinePrPublishError,
    publish_pr_to_stored_document,
)


@pytest.fixture
def fd_document() -> dict:
    path = Path(__file__).resolve().parents[1] / "content_guideline_documents.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["fd"]


def test_publish_pr_142_replaces_denosumab_paragraphs(fd_document: dict) -> None:
    published = publish_pr_to_stored_document(
        fd_document,
        pr_id="PR-142",
        reviewer="Dr. Test",
    )
    therapy = next(s for s in published["sections"] if s["id"] == "therapy")
    ids = [p["id"] for p in therapy["paragraphs"]]
    assert "tx-denosumab-1" not in ids
    assert "tx-denosumab-2" in ids
    para = next(p for p in therapy["paragraphs"] if p["id"] == "tx-denosumab-2")
    assert para.get("prInDiff") is None
    assert para["lastChange"]["type"] == "verified"


def test_publish_missing_paragraph_map_raises(fd_document: dict) -> None:
    with pytest.raises(GuidelinePrPublishError, match="paragraphMap"):
        publish_pr_to_stored_document(
            fd_document,
            pr_id="PR-999",
            reviewer="Dr. Test",
        )


@pytest.fixture
def mas_document() -> dict:
    path = Path(__file__).resolve().parents[1] / "content_guideline_documents.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["mas"]


@pytest.fixture
def noonan_document() -> dict:
    path = Path(__file__).resolve().parents[1] / "content_guideline_documents.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["noonan"]


def test_publish_pr_139_replaces_tanner_paragraph(mas_document: dict) -> None:
    published = publish_pr_to_stored_document(
        mas_document,
        pr_id="PR-139",
        reviewer="Dr. Test",
    )
    endocrine = next(s for s in published["sections"] if s["id"] == "endocrine")
    ids = [p["id"] for p in endocrine["paragraphs"]]
    assert "endo-tanner-old" not in ids
    assert "endo-tanner-1" in ids
    para = next(p for p in endocrine["paragraphs"] if p["id"] == "endo-tanner-1")
    assert para["lastChange"]["type"] == "verified"


def test_publish_pr_138_inserts_echo_followup(noonan_document: dict) -> None:
    published = publish_pr_to_stored_document(
        noonan_document,
        pr_id="PR-138",
        reviewer="Dr. Test",
    )
    cardiology = next(s for s in published["sections"] if s["id"] == "cardiology")
    assert any(p["id"] == "card-echo-followup" for p in cardiology["paragraphs"])
