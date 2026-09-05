"""Locks on the guideline pipeline's hard-won behaviour.

Everything pinned here was a real production defect, each found by a parent reading
the page rather than by a test. They are cheap to break again by accident while
working on something else — a prompt tidied up, a "magic number" reintroduced, a
fallback removed as dead code — and expensive to notice, because the symptom is a
worse guideline weeks later, not a red build.

If one of these fails, do not adjust the assertion to match the new behaviour
without reading why the assertion exists. The comment on each test is the reason.
"""

from __future__ import annotations

import json
import pathlib

import pytest

_SPECS = pathlib.Path(__file__).resolve().parents[1] / "flows" / "specs"


def _node(spec_name: str, node_id: str) -> dict:
    spec = json.loads((_SPECS / spec_name).read_text())
    return next(n for n in spec["nodes"] if n["node_id"] == node_id)


# --- shelf retrieval -------------------------------------------------------


def test_shelf_search_keeps_the_title_scoped_queries() -> None:
    """Without these, retrieval loses guideline documents that rank past 25.

    Measured on live PubMed: the three broad queries ranked "Clinical guidelines for
    the management of craniofacial fibrous dysplasia" 59th and "Fibrous dysplasia in
    children and its management" 51st, so production's shelf silently lost both —
    the two documents closest to a child with craniofacial disease. Title-scoped
    queries return few results and rank the right ones near the top.
    """
    from backend.executors.guidelines import guideline_shelf_search_executor as ex

    source = pathlib.Path(ex.__file__).read_text()

    assert "guideline*[Title]" in source
    assert "consensus[Title]" in source
    assert "management[Title]" in source
    assert "paediatric[Title]" in source or "pediatric[Title]" in source


def test_candidate_cap_is_high_enough_for_five_interleaved_queries() -> None:
    """Round-robin spreads each query's hits, so a rank-9 hit lands near position 45.

    At the old cap of 30 (and even at 40) the craniofacial guidelines were retrieved
    and then dropped again before the classifier ever saw them.
    """
    from backend.executors.guidelines.guideline_shelf_search_executor import _PUBMED_CANDIDATE_CAP

    assert _PUBMED_CANDIDATE_CAP >= 50


# --- shelf classification --------------------------------------------------


def test_classify_prompt_does_not_treat_a_newer_review_as_a_duplicate() -> None:
    """The 2023 NIH craniofacial review was dropped as a duplicate of 2012 guidelines.

    Both belong: the guideline is what was agreed, the review is where the field is
    now. The schema has kind=update + updates_note for exactly that relationship.
    """
    prompt = _node("guideline_shelf_build.json", "gsb-classify")["prompt"]

    assert "NOT duplicates when one is newer" in prompt


def test_classify_prompt_does_not_push_for_a_short_shelf() -> None:
    """"A tight, high-signal shelf beats a long one" cost us real documents.

    It was written when the prompt budget was unknown. The FD shelf is ~143 kB
    against a ~680 kB budget, so brevity buys nothing and costs a reader content.
    """
    prompt = _node("guideline_shelf_build.json", "gsb-classify")["prompt"]

    assert "tight, high-signal shelf beats" not in prompt


def test_classify_prompt_still_asks_for_the_rejection_reasons() -> None:
    """`considered` is what makes a removal visible instead of silent."""
    prompt = _node("guideline_shelf_build.json", "gsb-classify")["prompt"]

    assert "considered" in prompt
    assert "category" in prompt


# --- synthesis sections ----------------------------------------------------

_SECTIONS = ("diagnosis", "histopathology", "therapy", "surgery", "monitoring")


@pytest.mark.parametrize("section", _SECTIONS)
def test_every_section_prompt_demands_more_than_one_document(section: str) -> None:
    """Measured: this single sentence moved single-document sourcing from 7/10 runs
    to 1/8, over 18 runs against the real shelf on the production model. A longer,
    more verbose instruction block made it WORSE, so do not "improve" this by
    expanding it — measure with backend/scripts/synthesis_prompt_lab.py instead.
    """
    prompt = _node("guideline_synthesis.json", f"gs-sec-{section}")["prompt"]

    assert "not a safe default" in prompt


@pytest.mark.parametrize("section", _SECTIONS)
def test_every_section_prompt_asks_for_recommendations_not_definitions(section: str) -> None:
    """The synthesis used to read like an encyclopedia entry: what the disease IS
    rather than what should happen next. A parent has Wikipedia for the former.
    """
    prompt = _node("guideline_synthesis.json", f"gs-sec-{section}")["prompt"]

    assert "RECOMMENDS" in prompt
    assert "not what the disease IS" in prompt


@pytest.mark.parametrize("section", _SECTIONS)
def test_no_section_prompt_reintroduces_blanket_vagueness(section: str) -> None:
    """The old instruction to "stay at the level of patient guidance" was faithful to
    the vision but over-scoped into vagueness, and that is how the diagnostic
    pathway went missing. The vision excludes DOSING, not the decision itself.
    """
    prompt = _node("guideline_synthesis.json", f"gs-sec-{section}")["prompt"]

    assert "it does not mean vague" in prompt


@pytest.mark.parametrize("section", _SECTIONS)
def test_every_section_prompt_uses_full_text_when_there_is_full_text(section: str) -> None:
    """The shelf now carries open-access bodies, not just abstracts; the prompt has
    to know the difference, and say less when it only has an abstract.
    """
    prompt = _node("guideline_synthesis.json", f"gs-sec-{section}")["prompt"]

    assert "textSource" in prompt
    assert "full-text" in prompt


# --- full text -------------------------------------------------------------


def test_fulltext_falls_back_to_ncbi_when_europe_pmc_has_no_record() -> None:
    """Europe PMC 404s on PMC11087144 — the 2023 craniofacial review — while NCBI
    serves it in full. Without this fallback that paper contributes an abstract and
    loses to 60 kB of consensus text, which is exactly what happened.
    """
    from backend.tools import pmc_fulltext

    calls: list[str] = []

    class _Resp:
        def __init__(self, status: int, text: str) -> None:
            self.status_code = status
            self.text = text

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def get(self, url, params=None):
            calls.append(url)
            if "europepmc" in url:
                return _Resp(404, "")
            return _Resp(200, "<article><body><sec><title>Diagnosis</title>"
                              "<p>Biopsy is usually only necessary in questionable cases.</p>"
                              "</sec></body></article>")

    pmc_fulltext.httpx.Client = lambda **kw: _Client()  # type: ignore[assignment]
    try:
        out = pmc_fulltext.fetch_fulltext_sections("36849642", "PMC11087144")
    finally:
        import httpx as _real

        pmc_fulltext.httpx = _real

    assert any("europepmc" in c for c in calls), "Europe PMC must still be tried first"
    assert any("eutils.ncbi" in c for c in calls), "NCBI must be tried when Europe PMC 404s"
    assert out and "only necessary" in out[0][1]


def test_no_fixed_per_document_character_cap_survives() -> None:
    """A fixed cap discarded 36% of the FD consensus while the shelf used ~10% of the
    context. The budget must be derived from LLM_PROMPT_TOKEN_CAP.
    """
    from backend.executors.guidelines import guideline_shelf_load_executor as loader

    assert not hasattr(loader, "_FULLTEXT_CHARS_PER_DOC")
    # Big enough for a real guideline shelf, and derived rather than magic.
    assert loader._shelf_char_budget() > 100_000


def test_shelf_budget_follows_the_profile_that_is_actually_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production runs MODEL_PROFILE=vllm, which has its own tighter cap.

    Reading the general 200k cap instead let the FD shelf reach ~62.5k tokens of
    source text — over the vllm limit — with five section prompts each carrying it.
    """
    from backend import config
    from backend.executors.guidelines import guideline_shelf_load_executor as loader

    # SINGLE_LLM_MODE also forces the tighter budget, so pin it off to isolate the
    # profile itself. This dev machine runs with it on, which is why an earlier
    # version of this test passed for the wrong reason.
    monkeypatch.setattr(config, "SINGLE_LLM_MODE", False)
    monkeypatch.setenv("MODEL_PROFILE", "vllm")
    vllm_budget = loader._shelf_char_budget()
    monkeypatch.setenv("MODEL_PROFILE", "production")
    cloud_budget = loader._shelf_char_budget()

    assert vllm_budget < cloud_budget, "vllm must get the tighter budget"
    assert vllm_budget // loader._CHARS_PER_TOKEN < config.LLM_PROMPT_TOKEN_CAP_VLLM

    # And SINGLE_LLM_MODE alone is enough to trigger it, whatever the profile says.
    monkeypatch.setattr(config, "SINGLE_LLM_MODE", True)
    assert loader._shelf_char_budget() == vllm_budget
