"""Section handling in the synthesis writer: honest gaps, no recycled padding.

The five section headings are fixed, the literature behind them is not. Two rules
keep that from turning into filler:

- a section the shelf cannot support is kept and flagged ``noSource``, so the reader
  sees the gap instead of text quietly borrowed from another section;
- a paragraph that is an earlier section's paragraph rewritten is dropped, because
  section nodes run in parallel and no prompt can coordinate them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from backend.executors.base import NodeInput
from backend.executors.guideline_synthesis_writer_executor import (
    GuidelineSynthesisWriterExecutor,
    _near_duplicate,
    _text_fingerprint,
)

_SHELF = {"gs-shelf": {"ok": True, "shelf_docs": [{"docId": "d1", "pmid": "31196103"}]}}

_SPECS = [
    {"id": "diagnosis", "title": "1. Diagnosis"},
    {"id": "surgery", "title": "4. Indications for surgery"},
]

_INITIAL = {"disease_slug": "fd", "disease_name": "Fibrous Dysplasia", "sections": _SPECS}


def _para(pid: str, text: str) -> dict:
    return {"id": pid, "text": text, "source": {"doc": "d1", "loc": ""}, "citations": ["31196103"]}


def _sections(context: dict) -> list[dict]:
    executor = GuidelineSynthesisWriterExecutor()
    executor.execute  # noqa: B018 — keep the public entry point referenced
    return executor._collect_sections({**_SHELF, **context}, _SPECS, {})


def test_section_without_shelf_basis_is_kept_and_flagged() -> None:
    sections = _sections(
        {
            "gs-sec-diagnosis": {"paragraphs": [_para("p1", "Diagnosis rests on imaging and the GNAS finding.")]},
            "gs-sec-surgery": {"paragraphs": []},
        }
    )

    by_id = {s["id"]: s for s in sections}
    # The heading survives — a missing section would read as "nothing to say here".
    assert set(by_id) == {"diagnosis", "surgery"}
    assert by_id["surgery"]["noSource"] is True
    assert by_id["surgery"]["paragraphs"] == []
    assert "noSource" not in by_id["diagnosis"]


def test_section_missing_from_context_is_flagged_not_dropped() -> None:
    sections = _sections(
        {"gs-sec-diagnosis": {"paragraphs": [_para("p1", "Diagnosis rests on imaging.")]}}
    )

    by_id = {s["id"]: s for s in sections}
    assert by_id["surgery"]["noSource"] is True


def test_paragraph_restating_an_earlier_section_is_dropped() -> None:
    """Verbatim from the live osteogenesis imperfecta synthesis that motivated this.

    diagnosis/p2 came back a second time as histopathology/p2 with the opening clause
    swapped. Using the real pair keeps the threshold honest — a hand-written "rewrite"
    is easy to make more different than the model actually makes them.
    """
    shared = (
        "OI is a genetically heterogeneous group of inherited disorders. Approximately 90% of "
        "affected individuals are heterozygous for causative variants in the COL1A1 and COL1A2 "
        "genes. The remaining cases often involve recessively inherited forms of OI, with "
        "causative variants identified in genes such as CRTAP, FKBP10, LEPRE1, PLOD2, PPIB, "
        "SERPINF1, SERPINH1, and SP7."
    )
    rewritten = (
        "Current diagnostic standards emphasize the genetic heterogeneity of the disorder. "
        "Approximately 90% of individuals with OI possess heterozygous causative variants in "
        "the COL1A1 and COL1A2 genes. Other forms of the disease are recessively inherited, "
        "with causative variants found in genes such as CRTAP, FKBP10, LEPRE1, PLOD2, PPIB, "
        "SERPINF1, SERPINH1, and SP7."
    )
    sections = _sections(
        {
            "gs-sec-diagnosis": {"paragraphs": [_para("p1", shared)]},
            "gs-sec-surgery": {"paragraphs": [_para("p1", rewritten)]},
        }
    )

    by_id = {s["id"]: s for s in sections}
    assert len(by_id["diagnosis"]["paragraphs"]) == 1
    # The duplicate emptied the section, so it is now an honest gap.
    assert by_id["surgery"]["paragraphs"] == []
    assert by_id["surgery"]["noSource"] is True


def test_related_but_distinct_paragraphs_both_survive() -> None:
    """The filter must not eat two genuine claims that merely share vocabulary."""
    first = (
        "Imaging has a central role in positive diagnosis, differential diagnosis and "
        "follow-up, and a standardized radiologic approach is recommended so that typical "
        "bone lesions are recognised consistently across centres."
    )
    second = (
        "Surgery is indicated primarily to correct skeletal deformity and to address lesions "
        "prone to fracture; it is not the first-line answer to bone pain alone, which is "
        "managed medically before any operative plan is considered."
    )
    sections = _sections(
        {
            "gs-sec-diagnosis": {"paragraphs": [_para("p1", first)]},
            "gs-sec-surgery": {"paragraphs": [_para("p1", second)]},
        }
    )

    assert all(len(s["paragraphs"]) == 1 for s in sections)
    assert not any(s.get("noSource") for s in sections)


def test_duplicate_filter_ignores_short_fragments() -> None:
    """Short boilerplate lines are not evidence of recycling."""
    short = _text_fingerprint("Care is multidisciplinary.")
    assert _near_duplicate(short, short) is False


def test_writer_refuses_when_every_section_is_empty() -> None:
    """All sections flagged = an empty document; nothing worth persisting."""
    executor = GuidelineSynthesisWriterExecutor()
    out = asyncio.run(
        executor.execute(
            NodeInput(
                node_config={},
                context={**_SHELF, "gs-sec-diagnosis": {"paragraphs": []}, "gs-sec-surgery": {"paragraphs": []}},
                initial_data=_INITIAL,
            )
        )
    ).data

    assert out["ok"] is False
    assert "nothing to write" in out["error"].lower()


def test_section_prompts_sync_from_spec_on_existing_databases() -> None:
    """Prod keeps the prompt its flow row was seeded with; the sync must update it.

    The spec loader skips a flow that already exists, so shipping a new prompt in the
    JSON changes nothing on a live database without this step — the same trap that left
    Feature 4 inert.
    """
    from backend.database import get_flow_definition_nodes
    from backend.database_flow_ensures import (
        _sync_guideline_synthesis_section_prompts_from_spec,
    )

    _sync_guideline_synthesis_section_prompts_from_spec()

    nodes = {str(n["node_id"]): n for n in get_flow_definition_nodes("guideline_synthesis")}
    section_nodes = {nid: n for nid, n in nodes.items() if nid.startswith("gs-sec-")}
    if not section_nodes:
        return  # flow not seeded in this test DB

    import json as _json

    spec_path = Path(__file__).resolve().parents[1] / "flows" / "specs" / "guideline_synthesis.json"
    spec = {
        n["node_id"]: n.get("prompt") or ""
        for n in _json.loads(spec_path.read_text(encoding="utf-8"))["nodes"]
    }
    for nid, node in section_nodes.items():
        assert str(node.get("prompt") or "") == spec[nid], nid

    # Idempotent: a second pass changes nothing.
    _sync_guideline_synthesis_section_prompts_from_spec()
    again = {str(n["node_id"]): n for n in get_flow_definition_nodes("guideline_synthesis")}
    assert {k: again[k].get("prompt") for k in section_nodes} == {
        k: v.get("prompt") for k, v in section_nodes.items()
    }


def test_duplicate_filter_is_order_independent() -> None:
    """A real pair that slipped through: 0.58 one way, 0.34 the other.

    ``SequenceMatcher.ratio`` anchors on its second argument, so the verdict used to
    depend on which section happened to be written first.
    """
    diagnosis = _text_fingerprint(
        "Diagnosis is primarily based on the identification of the characteristic clinical "
        "triad consisting of severe growth deficiency, strabismus, and extensive dermal "
        "melanocytosis, often accompanied by intellectual disability."
    )
    histopathology = _text_fingerprint(
        "The clinical presentation of the syndrome is characterized by a combination of "
        "severe growth deficiency, strabismus, intellectual disability, and extensive "
        "dermal melanocytosis."
    )

    assert _near_duplicate(histopathology, diagnosis) is True
    assert _near_duplicate(diagnosis, histopathology) is True


def test_related_paragraphs_from_a_sound_document_survive_the_tighter_cut() -> None:
    """Guards the recalibrated 0.50 threshold against the healthy end of the corpus.

    The most similar cross-section pair in a sound live synthesis measured 0.40.
    """
    imaging = _text_fingerprint(
        "Imaging has a central role in positive diagnosis, differential diagnosis and "
        "follow-up, and a standardized radiologic approach is recommended so typical bone "
        "lesions are recognised consistently across centres."
    )
    surgery = _text_fingerprint(
        "Surgery is indicated primarily to correct skeletal deformity and to address lesions "
        "prone to fracture; it is not the first-line answer to bone pain alone, which is "
        "managed medically before any operative plan is considered."
    )

    assert _near_duplicate(surgery, imaging) is False
    assert _near_duplicate(imaging, surgery) is False
