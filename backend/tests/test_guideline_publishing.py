"""Unit tests for the PubMed → guideline-document mapper.

Pure function tests; no DB, no FastAPI. Pins the contract that the AI-draft
payload validates against ``GuidelineDocumentResponse`` and that the section
ordering, paragraph identity, and PMID extraction match what the public reader
will render for a freshly bootstrapped disease.
"""

from __future__ import annotations

import pytest

from backend.content.guideline_publishing import (
    GuidelinePublishError,
    build_ai_draft_document_payload,
)
from backend.content_models import GuidelineDocumentResponse


def _full_pubmed_output() -> dict[str, object]:
    """Shape mirroring ``pick_pubmed_canonical_payload`` output for CDKL5-style run."""
    return {
        "disease_name": "CDKL5 deficiency disorder",
        "guideline_html": "<section id='overview'><p>Top-level assembled HTML.</p></section>",
        "diagnostic_algorithm_html": (
            "<p>Sequencing of the CDKL5 gene confirms diagnosis "
            "(PMID: 23456789, PMID: 31196103).</p>"
        ),
        "treatment_steps_html": (
            "<p>Antiepileptic regimens; see "
            "https://pubmed.ncbi.nlm.nih.gov/22334455/ for review.</p>"
        ),
        "monitoring_protocol_html": "<p>Quarterly developmental assessment.</p>",
        "red_flags_html": "<p>Status epilepticus requires emergency care.</p>",
        "follow_up_schedule_html": "",
        "evidence_gaps_html": (
            "<p>Long-term outcomes data sparse — only "
            "<a href='/pubmed/30001234'>one cohort</a> followed beyond 10 years.</p>"
        ),
        "references": "Top references list…",
        "article_count": 136,
        "evidence_score": 68,
        "confidence_index": 82,
    }


def test_full_payload_validates_against_response_model():
    payload = build_ai_draft_document_payload(
        disease_slug="cdkl5-deficiency",
        disease_name="CDKL5 deficiency disorder",
        output_json=_full_pubmed_output(),
        execution_id="3a68e881-54c0-4264-8e13-f23d401cae18",
    )

    # The function validated internally; re-validate here as belt-and-braces.
    parsed = GuidelineDocumentResponse.model_validate(payload)
    assert parsed.slug == "cdkl5-deficiency"
    assert parsed.title.startswith("CDKL5 deficiency disorder")
    assert parsed.version == "ai-draft-3a68e881"
    assert parsed.status == "ai-draft"
    assert parsed.statusBy is None
    assert "136 articles" in parsed.basedOn
    assert "evidence score 68" in parsed.basedOn


def test_section_order_and_ids_match_mapping():
    payload = build_ai_draft_document_payload(
        disease_slug="cdkl5-deficiency",
        disease_name="CDKL5 deficiency disorder",
        output_json=_full_pubmed_output(),
        execution_id="abcdef12",
    )
    section_ids = [s["id"] for s in payload["sections"]]
    # follow-up_html is empty in fixture → skipped; others appear in mapping order.
    assert section_ids == [
        "diagnostics",
        "red-flags",
        "treatment",
        "monitoring",
        "evidence-gaps",
    ]
    # Each section has exactly one paragraph with the documented id pattern.
    for section in payload["sections"]:
        paragraphs = section["paragraphs"]
        assert len(paragraphs) == 1
        assert paragraphs[0]["id"] == f"ai-{section['id']}-1"


def test_pmid_extraction_from_three_url_styles():
    payload = build_ai_draft_document_payload(
        disease_slug="cdkl5-deficiency",
        disease_name="CDKL5",
        output_json=_full_pubmed_output(),
        execution_id="abcdef12",
    )
    by_id = {s["id"]: s for s in payload["sections"]}
    # PMID: 23456789, PMID: 31196103 → both extracted, sorted ascending.
    assert by_id["diagnostics"]["paragraphs"][0]["citations"] == [
        "23456789",
        "31196103",
    ]
    # pubmed.ncbi.nlm.nih.gov/22334455/ → extracted.
    assert by_id["treatment"]["paragraphs"][0]["citations"] == ["22334455"]
    # /pubmed/30001234 → extracted.
    assert by_id["evidence-gaps"]["paragraphs"][0]["citations"] == ["30001234"]
    # Monitoring section has no PMIDs in fixture.
    assert by_id["monitoring"]["paragraphs"][0]["citations"] == []


def test_empty_output_raises_publish_error():
    output = {
        "disease_name": "Something",
        "guideline_html": "",
        "diagnostic_algorithm_html": "",
        "treatment_steps_html": "",
        "monitoring_protocol_html": "",
        "red_flags_html": "",
        "follow_up_schedule_html": "",
        "evidence_gaps_html": "",
        "article_count": 0,
        "evidence_score": 0,
    }
    with pytest.raises(GuidelinePublishError, match="no renderable sections"):
        build_ai_draft_document_payload(
            disease_slug="lesch-nyhan-syndrome",
            disease_name="Lesch-Nyhan",
            output_json=output,
            execution_id="xyz",
        )


def test_missing_slug_raises_publish_error():
    with pytest.raises(GuidelinePublishError, match="disease_slug"):
        build_ai_draft_document_payload(
            disease_slug="",
            disease_name="CDKL5",
            output_json=_full_pubmed_output(),
            execution_id="xyz",
        )


def test_disease_name_fallback_chain():
    """Empty disease_name → fall back to output.disease_name; then to slug."""
    output = _full_pubmed_output()
    output["disease_name"] = "Disease From Output"
    payload = build_ai_draft_document_payload(
        disease_slug="cdkl5-deficiency",
        disease_name="",
        output_json=output,
        execution_id="abc",
    )
    assert payload["title"].startswith("Disease From Output")

    output_no_name = _full_pubmed_output()
    output_no_name["disease_name"] = ""
    payload2 = build_ai_draft_document_payload(
        disease_slug="cdkl5-deficiency",
        disease_name="",
        output_json=output_no_name,
        execution_id="abc",
    )
    assert payload2["title"].startswith("cdkl5-deficiency")


def test_pmid_citations_are_capped_and_deduped():
    # Synthesize 50 unique PMIDs in one section.
    big_html = " ".join(f"PMID: {10000000 + i}" for i in range(50))
    output = {
        "disease_name": "X",
        "diagnostic_algorithm_html": big_html + " PMID: 10000001 PMID: 10000001",
        "treatment_steps_html": "",
        "monitoring_protocol_html": "",
        "red_flags_html": "",
        "follow_up_schedule_html": "",
        "evidence_gaps_html": "",
        "article_count": 50,
        "evidence_score": 70,
    }
    payload = build_ai_draft_document_payload(
        disease_slug="x-disease",
        disease_name="X",
        output_json=output,
        execution_id="abc",
    )
    citations = payload["sections"][0]["paragraphs"][0]["citations"]
    # Capped at 30; sorted ascending; deduped.
    assert len(citations) == 30
    assert citations == sorted(citations, key=int)
    assert len(set(citations)) == len(citations)


def test_appends_full_draft_fallback_when_structured_output_is_sparse():
    output = {
        "disease_name": "Sparse Disease",
        "guideline_html": (
            "<h3>Complete draft</h3><p>Longer blob from the pipeline "
            "(PMID: 12345678).</p>"
        ),
        "diagnostic_algorithm_html": "<p>Only one mapped section.</p>",
        "treatment_steps_html": "",
        "monitoring_protocol_html": "",
        "red_flags_html": "",
        "follow_up_schedule_html": "",
        "evidence_gaps_html": "",
        "article_count": 12,
        "evidence_score": 55,
    }
    payload = build_ai_draft_document_payload(
        disease_slug="sparse-disease",
        disease_name="Sparse Disease",
        output_json=output,
        execution_id="abc",
    )
    section_ids = [s["id"] for s in payload["sections"]]
    assert section_ids == ["diagnostics", "full-draft"]
    full = payload["sections"][-1]
    assert full["title"] == "Full Draft (raw pipeline output)"
    assert full["paragraphs"][0]["id"] == "ai-full-draft-1"
    assert full["paragraphs"][0]["citations"] == ["12345678"]


def test_does_not_append_full_draft_when_structured_sections_are_rich():
    rich_text = "<p>" + ("A" * 450) + "</p>"
    output = {
        "disease_name": "Rich Disease",
        "guideline_html": "<p>Complete guideline blob.</p>",
        "diagnostic_algorithm_html": rich_text,
        "treatment_steps_html": rich_text,
        "monitoring_protocol_html": rich_text,
        "red_flags_html": "",
        "follow_up_schedule_html": "",
        "evidence_gaps_html": "",
        "article_count": 80,
        "evidence_score": 70,
    }
    payload = build_ai_draft_document_payload(
        disease_slug="rich-disease",
        disease_name="Rich Disease",
        output_json=output,
        execution_id="abc",
    )
    section_ids = [s["id"] for s in payload["sections"]]
    assert section_ids == ["diagnostics", "treatment", "monitoring"]


def test_appends_full_draft_fallback_when_exactly_two_structured_sections():
    output = {
        "disease_name": "Two Section Disease",
        "guideline_html": "<p>Complete blob.</p>",
        "diagnostic_algorithm_html": "<p>Diagnostic section.</p>",
        "treatment_steps_html": "<p>Treatment section.</p>",
        "monitoring_protocol_html": "",
        "red_flags_html": "",
        "follow_up_schedule_html": "",
        "evidence_gaps_html": "",
        "article_count": 10,
        "evidence_score": 40,
    }
    payload = build_ai_draft_document_payload(
        disease_slug="two-section-disease",
        disease_name="Two Section Disease",
        output_json=output,
        execution_id="abc",
    )
    section_ids = [s["id"] for s in payload["sections"]]
    assert section_ids == ["diagnostics", "treatment", "full-draft"]


def test_bracket_refs_produce_no_citations():
    """Bracket notation [14, 80] is an ordinal reference number, not a PMID.

    The extractor correctly returns nothing for bracket-only HTML. Callers that
    need PMIDs from bracket-style sections must either:
      - embed explicit `PMID: xxxxx` markers in the section HTML, or
      - rely on the references/evidence-gaps section where explicit PMIDs appear.
    This test pins that behaviour so it is not accidentally 'fixed' in a way
    that maps arbitrary numbers to invalid PMIDs.
    """
    bracket_html = (
        "<p>Spinal muscular atrophy (SMA) is caused by SMN1 deletions [14, 80].</p>"
        "<p>Nusinersen demonstrated survival benefit in infantile-onset SMA [42, 55].</p>"
        "<p>Newborn screening improves outcomes [1].</p>"
    )
    output = {
        "disease_name": "Spinal Muscular Atrophy",
        "guideline_html": bracket_html,
        "diagnostic_algorithm_html": bracket_html,
        "treatment_steps_html": "",
        "monitoring_protocol_html": "",
        "red_flags_html": "",
        "follow_up_schedule_html": "",
        "evidence_gaps_html": "",
        "article_count": 4,
        "evidence_score": 72,
    }
    payload = build_ai_draft_document_payload(
        disease_slug="sma",
        disease_name="Spinal Muscular Atrophy",
        output_json=output,
        execution_id="test-bracket",
    )
    # Bracket refs [N] are not PMIDs; no citations should be extracted.
    citations = payload["sections"][0]["paragraphs"][0]["citations"]
    assert citations == [], (
        "Bracket refs like [14, 80] are reference numbers, not PMIDs. "
        "Extracting them would produce invalid PMID values."
    )


def test_pmids_extracted_from_references_section():
    """When bracket-style sections have no PMIDs, the references/evidence-gaps
    section typically does.  Verify PMIDs extracted there appear in citations."""
    refs_html = (
        "<ol>"
        "<li>Finkel RS et al. Nusinersen vs Sham. N Engl J Med. "
        "PMID: 29091570</li>"
        "<li>Mercuri E et al. Nusinersen in type 2/3 SMA. N Engl J Med. "
        "<a href='https://pubmed.ncbi.nlm.nih.gov/29091571/'>PMID: 29091571</a></li>"
        "</ol>"
    )
    output = {
        "disease_name": "SMA",
        "guideline_html": "<p>See references section.</p>",
        "diagnostic_algorithm_html": "<p>Genetic testing [1].</p>",
        "treatment_steps_html": "<p>Nusinersen [2].</p>",
        "monitoring_protocol_html": "<p>Quarterly review [3].</p>",
        "red_flags_html": "",
        "follow_up_schedule_html": "",
        "evidence_gaps_html": refs_html,
        "article_count": 80,
        "evidence_score": 78,
    }
    payload = build_ai_draft_document_payload(
        disease_slug="sma",
        disease_name="SMA",
        output_json=output,
        execution_id="test-refs",
    )
    by_id = {s["id"]: s for s in payload["sections"]}
    # Individual sections with bracket-only refs → no citations.
    assert by_id["diagnostics"]["paragraphs"][0]["citations"] == []
    assert by_id["treatment"]["paragraphs"][0]["citations"] == []
    # References section has explicit PMIDs → extracted correctly.
    ref_citations = by_id["evidence-gaps"]["paragraphs"][0]["citations"]
    assert "29091570" in ref_citations
    assert "29091571" in ref_citations


def test_full_draft_only_when_all_mapped_sections_are_empty():
    output = {
        "disease_name": "Only HTML Disease",
        "guideline_html": "<p>Complete blob. PMID: 11111111.</p>",
        "diagnostic_algorithm_html": "",
        "treatment_steps_html": "",
        "monitoring_protocol_html": "",
        "red_flags_html": "",
        "follow_up_schedule_html": "",
        "evidence_gaps_html": "",
        "article_count": 5,
        "evidence_score": 30,
    }
    payload = build_ai_draft_document_payload(
        disease_slug="only-html-disease",
        disease_name="Only HTML Disease",
        output_json=output,
        execution_id="abc",
    )
    section_ids = [s["id"] for s in payload["sections"]]
    assert section_ids == ["full-draft"]
    assert payload["sections"][0]["paragraphs"][0]["citations"] == ["11111111"]
