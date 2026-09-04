"""A shelf rebuild may not silently drop a document.

The rebuild is a full replace driven by one stochastic classification. It lost good
documents twice: the paediatric review and the 2012 craniofacial guidelines on one
run, the 2023 NIH craniofacial review on another. Both times the only symptom was a
worse synthesis, noticed by a human days later.

So a document already on the shelf is now carried forward unless this run's
``considered`` list names it with a reason category that justifies removal. The
classifier keeps full authority to supersede and de-duplicate — it simply cannot
drop something by forgetting it.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.executors.guideline_shelf_write_executor import _merge_with_existing


@dataclass
class _Doc:
    doc_id: str
    role: str = "Subtopic"
    title: str = "A paper"
    authors: str = "Boyce A"
    journal: str = "J"
    year: str = "2023"
    scope: str = "craniofacial"
    covers: tuple = ()
    pmid: str | None = None
    bookshelf: str | None = None
    free_full_text: bool = False
    updates_note: str | None = None

    def __post_init__(self) -> None:
        if self.pmid is None and self.doc_id.isdigit():
            self.pmid = self.doc_id


class _Repo:
    def __init__(self, existing: list[_Doc]) -> None:
        self._existing = existing

    def list_source_documents(self, slug: str) -> list[_Doc]:
        return self._existing


def _new(doc_id: str) -> dict:
    return {"id": doc_id, "title": "new", "role": "Base consensus"}


def test_a_document_the_classifier_forgot_is_carried_forward() -> None:
    """The exact failure: Boyce 2023 vanished with no reason given."""
    repo = _Repo([_Doc("36849642"), _Doc("31196103")])

    docs, kept = _merge_with_existing(repo, "fd", [_new("31196103")], considered=[])

    assert kept == {"36849642"}
    assert {d["id"] for d in docs} == {"31196103", "36849642"}


def test_a_superseded_document_is_allowed_to_go() -> None:
    repo = _Repo([_Doc("22640797"), _Doc("31196103")])
    considered = [{"pmid": "22640797", "reason": "replaced by the 2019 consensus", "category": "superseded"}]

    docs, kept = _merge_with_existing(repo, "fd", [_new("31196103")], considered)

    assert kept == set()
    assert {d["id"] for d in docs} == {"31196103"}


def test_a_duplicate_or_off_topic_document_is_allowed_to_go() -> None:
    repo = _Repo([_Doc("111"), _Doc("222"), _Doc("31196103")])
    considered = [
        {"pmid": "111", "reason": "same content", "category": "duplicate"},
        {"pmid": "222", "reason": "different entity", "category": "off-topic"},
    ]

    docs, kept = _merge_with_existing(repo, "fd", [_new("31196103")], considered)

    assert kept == set()
    assert {d["id"] for d in docs} == {"31196103"}


def test_a_weak_reason_is_not_enough_to_drop_a_document() -> None:
    """"narrow" or "other" is an opinion, not a justification — the document stays."""
    repo = _Repo([_Doc("36849642"), _Doc("31196103")])
    considered = [{"pmid": "36849642", "reason": "quite specific", "category": "narrow"}]

    docs, kept = _merge_with_existing(repo, "fd", [_new("31196103")], considered)

    assert kept == {"36849642"}


def test_bookshelf_documents_are_carried_forward_too() -> None:
    repo = _Repo([_Doc("NBK274564", pmid=None, bookshelf="NBK274564")])

    docs, kept = _merge_with_existing(repo, "fd", [_new("31196103")], considered=[])

    assert kept == {"NBK274564"}
    carried = next(d for d in docs if d["id"] == "NBK274564")
    assert carried["bookshelf"] == "NBK274564"
    # A carried-forward document is not "new" — that badge belongs to this run's finds.
    assert carried["isNew"] is False


def test_reselected_documents_are_not_duplicated() -> None:
    repo = _Repo([_Doc("31196103")])

    docs, kept = _merge_with_existing(repo, "fd", [_new("31196103")], considered=[])

    assert kept == set()
    assert [d["id"] for d in docs] == ["31196103"]


def test_an_unreadable_previous_shelf_degrades_to_a_plain_replace() -> None:
    """A rebuild must not fail because the audit read failed."""

    class _Broken:
        def list_source_documents(self, slug: str):
            raise RuntimeError("db down")

    docs, kept = _merge_with_existing(_Broken(), "fd", [_new("31196103")], considered=[])

    assert kept == set()
    assert [d["id"] for d in docs] == ["31196103"]
