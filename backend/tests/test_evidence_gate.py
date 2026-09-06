"""A synthesis that cites nothing must never reach a reader.

This is not hypothetical. severe-growth-deficiency-strabismus-extensive-dermal-
melanocytos was publicly listed for a month showing 1,846 characters of fluent,
uncited prose — "The diagnosis is primarily suggested by the presence of a distinct
constellation of clinical manifestations", "There is currently no specific curative
therapy" — generated from a shelf of two GeneReviews fragments with no readable text.
The run completed, five sections appeared, nothing anywhere went red.

Padding is the worst output this system can produce. A thin guideline invites a
reader to check the sources; a confident generic one does not.

The gate is enforced twice on purpose. The writer refuses so no new padding is
stored; the read path withholds so padding already in the database stops being served
without waiting for a migration.
"""

from __future__ import annotations

from backend.guidelines.evidence import cited_source_ids, is_grounded


def _para(*source_ids: str, loc: str = "") -> dict:
    """A stored paragraph. `source.doc` is always present — the writer requires it,
    which is precisely why it cannot serve as the grounding signal."""
    return {
        "text": "Some clinical prose.",
        "source": {"doc": source_ids[0] if source_ids else "NBK621299", "loc": loc},
        "citations": [{"sourceId": s} for s in source_ids],
    }


def _sections(*paragraph_groups: list[dict]) -> list[dict]:
    return [{"id": f"s{i}", "paragraphs": g} for i, g in enumerate(paragraph_groups)]


def test_prose_citing_nothing_is_not_grounded() -> None:
    """The exact shape that shipped: attributed to a real shelf document, but with no
    citation and no position inside it — the model never read a word of it."""
    assert is_grounded(_sections([_para(), _para()])) is False


def test_attribution_alone_never_counts_as_grounding() -> None:
    """The trap this gate nearly fell into. Every stored paragraph carries a
    source.doc because the writer rejects paragraphs without one, so a gate keyed on
    source.doc would pass the padded document unchanged."""
    padded = _sections([_para()])

    assert padded[0]["paragraphs"][0]["source"]["doc"]
    assert is_grounded(padded) is False


def test_a_bookshelf_only_synthesis_is_publishable() -> None:
    """GeneReviews entries have no PMID, so a citations-only gate would withhold a
    perfectly honest guideline built from them. A position inside the document is
    proof the model read it."""
    assert is_grounded(_sections([_para(loc="§ Diagnosis")])) is True


def test_one_real_citation_is_enough_to_publish() -> None:
    """A thin guideline is still a guideline — it points somewhere checkable."""
    assert is_grounded(_sections([_para("31196103")])) is True


def test_an_empty_document_is_not_grounded() -> None:
    assert is_grounded([]) is False
    assert is_grounded(None) is False


def test_distinct_sources_are_counted_once_each() -> None:
    sections = _sections([_para("1", "2"), _para("2")], [_para("3")])

    assert cited_source_ids(sections) == {"1", "2", "3"}


def test_blank_and_malformed_citations_do_not_count_as_evidence() -> None:
    """An empty sourceId is not a source; counting it would let padding through the
    gate wearing a citation's clothes."""
    sections = [
        {"paragraphs": [{"citations": [{"sourceId": ""}, {"sourceId": None}]}]},
        {"paragraphs": [{"citations": ["  "]}]},
        "not a section",
        {"paragraphs": ["not a paragraph"]},
    ]

    assert cited_source_ids(sections) == set()
    assert is_grounded(sections) is False


def test_both_citation_key_spellings_are_read() -> None:
    """The API renders sourceId, storage has carried source_id — a gate that only
    knew one spelling would withhold healthy guidelines."""
    assert cited_source_ids([{"paragraphs": [{"citations": [{"source_id": "42"}]}]}]) == {"42"}


def test_the_read_path_withholds_an_ungrounded_synthesis(monkeypatch) -> None:
    """Fixes production without a migration: the row stays, the page stops showing it."""
    from backend.guidelines import service as svc

    padded = _synthesis(sections=_sections([_para()]))
    grounded = _synthesis(sections=_sections([_para("31196103")]))

    assert _served(svc, monkeypatch, padded) is None
    assert _served(svc, monkeypatch, grounded) is not None


def _synthesis(*, sections: list[dict]):
    from backend.guidelines.models import GuidelineSynthesis

    return GuidelineSynthesis(
        disease_slug="x",
        kind="synthesis",
        title="t",
        version="v",
        last_updated="2026-09-06",
        based_on="b",
        synth_disclaimer="d",
        status="draft",
        epistemic_level="a",
        has_flowchart=False,
        source_ids=[],
        sections=sections,
        what_to_do_now=None,
        red_flags=None,
    )


def _served(svc, monkeypatch, synthesis):
    class _Repo:
        def get_synthesis(self, slug: str):
            return synthesis

    service = svc.GuidelinesService.__new__(svc.GuidelinesService)
    object.__setattr__(service, "repo", _Repo())
    object.__setattr__(service, "synthesis_translation_repo", None)
    return service.get_synthesis("x")
