"""Tests for Feature 4 — per-claim grounded source paraphrases ("Where we know
this from").

In-memory SQLite (StaticPool) + the GL-4 pattern; no network. Covers:

  - the ``guideline_quotes`` preset + its Pydantic guardrails (SourceQuote /
    GuidelineParagraphQuotes / GuidelineQuoteExtractionOutput),
  - the ``guideline_quote_extract_load`` executor (builds claims + cited
    abstracts from the in-run synthesis context, zero extra PubMed calls),
  - the writer's deterministic quote-merge gate (supported-only; PMID must be
    among the paragraph's citations; anti-copyright truncation),
  - the flow-spec / registry wiring.

The paraphrases themselves are LLM judgement — there is no deterministic ground
truth to assert; these tests pin the plumbing and the guardrails around it.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

import backend.guidelines.orm  # noqa: F401 — registers tables on the shared metadata
from backend.agents.schemas import (
    PRESET_OUTPUT_SCHEMAS,
    SOURCE_QUOTE_MAX_CHARS,
    GuidelineParagraph,
    GuidelineParagraphQuotes,
    GuidelineQuoteExtractionOutput,
    SourceQuote,
)
from backend.executors import EXECUTOR_REGISTRY
from backend.executors.base import NodeInput
from backend.executors.guideline_quote_extract_load_executor import (
    GuidelineQuoteExtractLoadExecutor,
)
from backend.executors.guideline_synthesis_writer_executor import (
    GuidelineSynthesisWriterExecutor,
    _collect_quotes,
    _gate_quotes,
)
from backend.guidelines.repository import SqlaGuidelinesRepo
from backend.shared.persistence.schema import metadata


@pytest.fixture
def repo() -> SqlaGuidelinesRepo:
    engine = create_engine(
        "sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    return SqlaGuidelinesRepo(engine=engine)


# ── preset registration ────────────────────────────────────────────────────


def test_quotes_preset_registered() -> None:
    assert PRESET_OUTPUT_SCHEMAS.get("guideline_quotes") is GuidelineQuoteExtractionOutput


# ── SourceQuote guardrails ─────────────────────────────────────────────────


def test_source_quote_accepts_valid() -> None:
    q = SourceQuote(pmid="31196103", paraphrase="In our own words.", supports="the imaging point")
    assert q.pmid == "31196103"
    assert q.doc == ""  # optional, defaults empty


def test_source_quote_rejects_non_digit_pmid() -> None:
    with pytest.raises(ValidationError):
        SourceQuote(pmid="PMID-31196103", paraphrase="x")


def test_source_quote_rejects_empty_paraphrase() -> None:
    with pytest.raises(ValidationError):
        SourceQuote(pmid="31196103", paraphrase="")


def test_source_quote_rejects_overlong_paraphrase() -> None:
    with pytest.raises(ValidationError):
        SourceQuote(pmid="31196103", paraphrase="x" * (SOURCE_QUOTE_MAX_CHARS + 1))


def test_source_quote_none_optionals_become_empty() -> None:
    q = SourceQuote(pmid="31196103", paraphrase="p", doc=None, supports=None)
    assert q.doc == "" and q.supports == ""


# ── GuidelineParagraphQuotes verdict / GuidelineQuoteExtractionOutput ───────


def test_paragraph_quotes_default_verdict_is_supported() -> None:
    pq = GuidelineParagraphQuotes(section_id="diagnosis", paragraph_id="dx1")
    assert pq.verdict == "supported"
    assert pq.quotes == []


def test_paragraph_quotes_rejects_bad_verdict() -> None:
    with pytest.raises(ValidationError):
        GuidelineParagraphQuotes(section_id="s", paragraph_id="p", verdict="probably")


def test_paragraph_quotes_accepts_all_valid_verdicts() -> None:
    for verdict in ("supported", "unsupported", "uncertain"):
        pq = GuidelineParagraphQuotes(section_id="s", paragraph_id="p", verdict=verdict)
        assert pq.verdict == verdict


def test_quote_extraction_output_empty_is_valid() -> None:
    assert GuidelineQuoteExtractionOutput(paragraphs=[]).paragraphs == []


def test_guideline_paragraph_carries_optional_quotes() -> None:
    """The synthesis paragraph schema gained an additive, optional ``quotes`` list."""
    p = GuidelineParagraph(
        id="dx1",
        text="A claim.",
        source={"doc": "boyce2019", "loc": "§X"},
        citations=["31196103"],
        quotes=[{"pmid": "31196103", "paraphrase": "Our words."}],
    )
    assert p.quotes[0].pmid == "31196103"
    # Absent quotes default to an empty list (backwards compatible).
    p2 = GuidelineParagraph(id="dx2", text="t", source={"doc": "d"})
    assert p2.quotes == []


# ── quote-extract-load executor ─────────────────────────────────────────────


def _load_context() -> dict:
    return {
        "gs-shelf": {
            "shelf_docs": [
                {
                    "docId": "boyce2019",
                    "pmid": "31196103",
                    "title": "Consensus",
                    "abstract": "A bone scan is done once at diagnosis.",
                },
                {"docId": "genereviews", "pmid": None, "title": "GeneReviews", "abstract": ""},
            ]
        },
        "gs-sec-diagnosis": {
            "id": "diagnosis",
            "paragraphs": [
                {
                    "id": "dx-scan",
                    "text": "A bone scan is done only once at diagnosis.",
                    "source": {"doc": "boyce2019", "loc": "§ Imaging"},
                    "citations": ["31196103"],
                }
            ],
        },
    }


def test_quote_load_builds_claims_and_sources() -> None:
    initial = {"disease_slug": "fd", "sections": [{"id": "diagnosis", "title": "1. Diagnosis"}]}
    ex = GuidelineQuoteExtractLoadExecutor()
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context=_load_context(), initial_data=initial))
    )
    assert out.data["ok"] is True
    assert out.data["claim_count"] == 1
    claim = out.data["claims"][0]
    assert claim["section_id"] == "diagnosis"
    assert claim["paragraph_id"] == "dx-scan"
    assert claim["cited_doc"] == "boyce2019"
    # docId's own PMID is surfaced even though it is also in citations.
    assert claim["cited_pmid"] == "31196103"
    assert claim["citations"] == ["31196103"]
    sources = {s["docId"]: s for s in out.data["sources"]}
    assert sources["boyce2019"]["abstract"] == "A bone scan is done once at diagnosis."
    assert sources["genereviews"]["pmid"] is None


def test_quote_load_errors_without_slug() -> None:
    ex = GuidelineQuoteExtractLoadExecutor()
    out = asyncio.run(ex.execute(NodeInput(node_config={}, context={}, initial_data={})))
    assert out.data["ok"] is False
    assert "disease_slug" in out.data["error"].lower()


def test_quote_load_errors_without_sections() -> None:
    ex = GuidelineQuoteExtractLoadExecutor()
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context={}, initial_data={"disease_slug": "fd"}))
    )
    assert out.data["ok"] is False
    assert "section" in out.data["error"].lower()


def test_quote_load_errors_when_no_paragraphs_in_context() -> None:
    initial = {"disease_slug": "fd", "sections": [{"id": "diagnosis", "title": "1. Diagnosis"}]}
    ex = GuidelineQuoteExtractLoadExecutor()
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context={}, initial_data=initial))
    )
    assert out.data["ok"] is False
    assert "paragraph" in out.data["error"].lower()


def test_quote_load_executor_registered() -> None:
    assert EXECUTOR_REGISTRY["guideline_quote_extract_load"] is GuidelineQuoteExtractLoadExecutor


# ── writer merge gate: _collect_quotes / _gate_quotes ───────────────────────


def test_collect_quotes_indexes_supported_only() -> None:
    raw = {
        "paragraphs": [
            {"section_id": "diagnosis", "paragraph_id": "a", "verdict": "supported",
             "quotes": [{"pmid": "1", "paraphrase": "p"}]},
            {"section_id": "diagnosis", "paragraph_id": "b", "verdict": "unsupported",
             "quotes": [{"pmid": "1", "paraphrase": "p"}]},
            {"section_id": "diagnosis", "paragraph_id": "c", "verdict": "uncertain",
             "quotes": [{"pmid": "1", "paraphrase": "p"}]},
            # Missing verdict → treated as supported (default).
            {"section_id": "diagnosis", "paragraph_id": "d",
             "quotes": [{"pmid": "1", "paraphrase": "p"}]},
        ]
    }
    index = _collect_quotes(raw)
    assert set(index.keys()) == {("diagnosis", "a"), ("diagnosis", "d")}


def test_collect_quotes_skips_entries_missing_ids() -> None:
    raw = {"paragraphs": [{"paragraph_id": "a", "quotes": [{"pmid": "1", "paraphrase": "p"}]}]}
    assert _collect_quotes(raw) == {}


def test_collect_quotes_handles_non_dict() -> None:
    assert _collect_quotes(None) == {}
    assert _collect_quotes([]) == {}


def test_gate_drops_pmid_not_in_citations() -> None:
    quotes = [{"pmid": "99999999", "paraphrase": "not cited"}]
    assert _gate_quotes(quotes, citations=["31196103"]) == []


def test_gate_drops_non_digit_pmid_and_empty_paraphrase() -> None:
    quotes = [
        {"pmid": "not-a-pmid", "paraphrase": "x"},
        {"pmid": "31196103", "paraphrase": "   "},
    ]
    assert _gate_quotes(quotes, citations=["31196103", "not-a-pmid"]) == []


def test_gate_keeps_valid_quote_and_normalizes_whitespace() -> None:
    quotes = [{"pmid": "31196103", "paraphrase": "our\n  words   here", "doc": "boyce2019", "supports": "point"}]
    out = _gate_quotes(quotes, citations=["31196103"])
    assert out == [
        {"pmid": "31196103", "paraphrase": "our words here", "doc": "boyce2019", "supports": "point"}
    ]


def test_gate_truncates_to_anti_copyright_ceiling() -> None:
    long_paraphrase = "x" * (SOURCE_QUOTE_MAX_CHARS + 100)
    out = _gate_quotes([{"pmid": "31196103", "paraphrase": long_paraphrase}], citations=["31196103"])
    assert len(out) == 1
    text = out[0]["paraphrase"]
    assert text.endswith("…")
    assert len(text) == SOURCE_QUOTE_MAX_CHARS + 1  # 400 chars + the single ellipsis


# ── writer end-to-end merge (assembly → GL-4) ───────────────────────────────


def _writer_context(verdict: str, quote_pmid: str, para_citations: list[str]) -> dict:
    return {
        "gs-shelf": {"shelf_docs": [{"docId": "boyce2019", "pmid": "31196103"}]},
        "gs-sec-diagnosis": {
            "id": "diagnosis",
            "intro": "i",
            "paragraphs": [
                {
                    "id": "dx1",
                    "text": "A synthesised claim.",
                    "source": {"doc": "boyce2019", "loc": "§X"},
                    "citations": para_citations,
                }
            ],
        },
        "gs-quotes": {
            "paragraphs": [
                {
                    "section_id": "diagnosis",
                    "paragraph_id": "dx1",
                    "verdict": verdict,
                    "quotes": [{"pmid": quote_pmid, "paraphrase": "In our own words."}],
                }
            ]
        },
    }


_WRITER_INITIAL = {
    "disease_slug": "fd",
    "disease_name": "Fibrous Dysplasia",
    "sections": [{"id": "diagnosis", "title": "1. Diagnosis"}],
}


def _run_writer(repo: SqlaGuidelinesRepo, context: dict) -> dict:
    ex = GuidelineSynthesisWriterExecutor(repo=repo)
    out = asyncio.run(
        ex.execute(NodeInput(node_config={}, context=context, initial_data=_WRITER_INITIAL))
    )
    assert out.data["ok"] is True
    syn = repo.get_synthesis("fd")
    assert syn is not None
    return syn.sections[0]["paragraphs"][0]


def test_writer_merges_supported_quote(repo: SqlaGuidelinesRepo) -> None:
    para = _run_writer(repo, _writer_context("supported", "31196103", ["31196103"]))
    assert para["quotes"] == [{"pmid": "31196103", "paraphrase": "In our own words."}]


def test_writer_omits_quote_for_unsupported_claim(repo: SqlaGuidelinesRepo) -> None:
    para = _run_writer(repo, _writer_context("unsupported", "31196103", ["31196103"]))
    assert "quotes" not in para


def test_writer_omits_quote_for_uncertain_claim(repo: SqlaGuidelinesRepo) -> None:
    para = _run_writer(repo, _writer_context("uncertain", "31196103", ["31196103"]))
    assert "quotes" not in para


def test_writer_drops_quote_whose_pmid_is_not_cited(repo: SqlaGuidelinesRepo) -> None:
    # Supported, but the quote attributes a PMID the paragraph does not cite → gated out.
    para = _run_writer(repo, _writer_context("supported", "99999999", ["31196103"]))
    assert "quotes" not in para


def test_writer_without_quotes_node_is_unchanged(repo: SqlaGuidelinesRepo) -> None:
    context = _writer_context("supported", "31196103", ["31196103"])
    del context["gs-quotes"]  # older flow: no quote-extraction node ran
    para = _run_writer(repo, context)
    assert "quotes" not in para
    assert para["text"] == "A synthesised claim."
