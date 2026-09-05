"""Open-access full text reaches the synthesis prompt instead of just the abstract.

Why this file exists. The FD synthesis on production read like an encyclopedia entry
and omitted the one fact that mattered most to the founder — that the FD/MAS
consensus says a biopsy is usually unnecessary in typical cases. The cause was not
the model: the shelf loader put only PubMed *abstracts* into the prompt, and the
consensus abstract contains zero occurrences of "biopsy", "histolog",
"scintigraph" or "radiograph" while its open-access full text contains all four.

These tests pin the two elink traps that made the first implementation return the
wrong article entirely, and the fallback behaviour that keeps a closed-access
document working.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from backend.tools import pmc_fulltext


class _FakeResponse:
    def __init__(self, *, json_data=None, text: str = "", status_code: int = 200) -> None:
        self._json = json_data
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    """Captures the request so the tests can assert on how elink was called."""

    def __init__(self, response: _FakeResponse, sink: dict) -> None:
        self._response = response
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def get(self, url, params=None):
        self._sink["url"] = url
        self._sink["params"] = params
        return self._response


def _elink_payload() -> dict:
    """Shape of a real two-id elink reply, including the citing-articles linkset."""
    return {
        "linksets": [
            {
                "ids": ["31196103"],
                "linksetdbs": [
                    {"linkname": "pubmed_pmc", "links": ["6567644"]},
                    # The trap: ~150 articles that CITE this one, listed second.
                    {"linkname": "pubmed_pmc_refs", "links": ["11087144", "13413209"]},
                ],
            },
            {
                "ids": ["36849642"],
                "linksetdbs": [{"linkname": "pubmed_pmc", "links": ["11087144"]}],
            },
        ]
    }


def test_pmid_to_pmcid_ignores_the_citing_articles_linkset(monkeypatch: pytest.MonkeyPatch) -> None:
    """`pubmed_pmc_refs` is who cites the paper, not the paper. Taking the first
    linksetdb returned a different 2023 review for the FD consensus."""
    sink: dict = {}
    monkeypatch.setattr(
        pmc_fulltext.httpx,
        "Client",
        lambda **kw: _FakeClient(_FakeResponse(json_data=_elink_payload()), sink),
    )

    out = pmc_fulltext._pmid_to_pmcid(["31196103", "36849642"])

    assert out == {"31196103": "PMC6567644", "36849642": "PMC11087144"}


def test_pmid_to_pmcid_sends_one_id_param_per_pmid(monkeypatch: pytest.MonkeyPatch) -> None:
    """A comma-joined `id=` collapses every input into ONE merged linkset, which
    destroys the PMID→PMCID pairing. Repeated `id=` params keep them separate."""
    sink: dict = {}
    monkeypatch.setattr(
        pmc_fulltext.httpx,
        "Client",
        lambda **kw: _FakeClient(_FakeResponse(json_data=_elink_payload()), sink),
    )

    pmc_fulltext._pmid_to_pmcid(["31196103", "36849642"])

    params = sink["params"]
    assert [v for k, v in params if k == "id"] == ["31196103", "36849642"]
    assert ("linkname", "pubmed_pmc") in params


def test_pmid_to_pmcid_soft_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead NCBI must degrade to abstracts, never break a research run."""

    def _boom(**kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(pmc_fulltext.httpx, "Client", _boom)

    assert pmc_fulltext._pmid_to_pmcid(["31196103"]) == {}


_JATS = """<article><body>
<sec><title>Diagnosis</title>
<p>In most cases, the diagnosis of FD/MAS can be made clinically after a complete staging evaluation.</p>
<sec><title>Imaging</title>
<p>Technetium-99 scintigraphy establishes the extent of skeletal involvement without biopsy.</p>
</sec></sec>
<sec><title>Histological and genetic characterisation</title>
<p>Biopsy with histological evaluation is usually only necessary in unusual or questionable cases.</p>
</sec>
<sec><title>References</title>
<p>Javaid MK, Boyce A, Appelman-Dijkstra N, et al. Orphanet J Rare Dis 2019 and many more entries.</p>
</sec>
</body></article>"""


def test_fetch_fulltext_sections_keeps_headings_and_drops_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pmc_fulltext.httpx,
        "Client",
        lambda **kw: _FakeClient(_FakeResponse(text=_JATS), {}),
    )

    out = pmc_fulltext.fetch_fulltext_sections("31196103", "PMC6567644")

    titles = [t for t, _ in out]
    assert "Diagnosis" in titles
    # Nested <sec> keeps its own heading, so provenance points at the real section.
    assert "Imaging" in titles
    assert "Histological and genetic characterisation" in titles
    # The reference list is noise that would crowd out content under the budget.
    assert "References" not in titles
    body = " ".join(text for _, text in out)
    assert "Biopsy with histological evaluation" in body
    assert "scintigraphy" in body


def test_render_for_prompt_labels_sections_and_respects_the_budget() -> None:
    sections = [("Diagnosis", "A" * 100), ("Diagnosis", "B" * 100), ("Imaging", "C" * 100)]

    rendered = pmc_fulltext.render_for_prompt(sections, char_budget=250)

    assert "### Diagnosis" in rendered
    # Heading emitted once per run of paragraphs, not per paragraph.
    assert rendered.count("### Diagnosis") == 1
    # Truncation happens at a whole paragraph, never mid-sentence.
    assert "C" * 100 not in rendered
    assert len(rendered) <= 250


def test_render_for_prompt_handles_an_empty_shelf() -> None:
    assert pmc_fulltext.render_for_prompt([], char_budget=1000) == ""


def test_fetch_fulltext_by_pmid_skips_documents_without_open_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A closed-access document simply has no key — the caller falls back to its
    abstract, which is exactly what the pipeline did before full text existed."""
    monkeypatch.setattr(
        pmc_fulltext, "_pmid_to_pmcid", lambda pmids, api_key=None: {"31196103": "PMC6567644"}
    )
    monkeypatch.setattr(
        pmc_fulltext,
        "fetch_fulltext_sections",
        lambda pmid, pmcid, api_key=None: [
            ("Diagnosis", "Clinically diagnosable in most cases without biopsy.")
        ],
    )

    out = pmc_fulltext.fetch_fulltext_by_pmid(["31196103", "40186713"], char_budget=10_000)

    assert set(out) == {"31196103"}
    assert "without biopsy" in out["31196103"]


def test_malformed_xml_returns_empty_rather_than_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pmc_fulltext,
        "httpx",
        type("_M", (), {"Client": lambda **kw: _FakeClient(_FakeResponse(text="<not xml"), {})})(),
    )

    assert pmc_fulltext.fetch_fulltext_sections("1", "PMC1") == []


def test_pmc_url_points_at_the_reader() -> None:
    assert pmc_fulltext.pmc_url("PMC6567644") == "https://pmc.ncbi.nlm.nih.gov/articles/PMC6567644/"


def test_jats_fixture_is_valid_xml() -> None:
    """Guards the fixture itself, so a broken fixture cannot fake a passing suite."""
    assert ET.fromstring(_JATS).find(".//body") is not None


# --- shelf-level budgeting -------------------------------------------------
# A fixed per-document cap threw away 36% of the FD consensus while the shelf as a
# whole used ~10% of the token budget. These pin the replacement: cut nothing while
# there is room, and when there isn't, cut the big documents rather than the small
# ones.


def test_fit_shelf_trims_nothing_when_the_shelf_fits() -> None:
    shelf = {"a": "x" * 1000, "b": "y" * 2000}

    assert pmc_fulltext.fit_shelf_to_budget(shelf, 100_000) == shelf


def test_fit_shelf_cuts_the_largest_document_not_the_smallest() -> None:
    """Water-filling: a small paper keeps every sentence when a big one overflows."""
    shelf = {"small": "s" * 1_000, "huge": "h" * 100_000}

    out = pmc_fulltext.fit_shelf_to_budget(shelf, 20_000)

    assert out["small"] == shelf["small"]  # untouched
    assert len(out["huge"]) < len(shelf["huge"])
    assert sum(len(v) for v in out.values()) <= 20_000


def test_fit_shelf_spreads_the_cut_when_everything_is_oversized() -> None:
    shelf = {"a": "a" * 60_000, "b": "b" * 60_000}

    out = pmc_fulltext.fit_shelf_to_budget(shelf, 40_000)

    assert sum(len(v) for v in out.values()) <= 40_000
    # Neither document is starved to make room for the other.
    assert all(len(v) > 15_000 for v in out.values())


def test_fit_shelf_cuts_at_a_paragraph_boundary() -> None:
    shelf = {"a": "\n".join("para " + "x" * 100 for _ in range(50))}

    out = pmc_fulltext.fit_shelf_to_budget(shelf, 2_000)

    assert not out["a"].endswith("x" * 5) or "\n" in out["a"]
    assert len(out["a"]) <= 2_000


def test_fit_shelf_handles_an_empty_shelf() -> None:
    assert pmc_fulltext.fit_shelf_to_budget({}, 1_000) == {}


def test_shelf_budget_is_derived_from_the_token_cap() -> None:
    """The budget must follow LLM_PROMPT_TOKEN_CAP, not a magic constant."""
    from backend.executors.guidelines import guideline_shelf_load_executor as loader

    budget = loader._shelf_char_budget()

    assert budget > 100_000  # a real guideline shelf must fit whole
    assert budget < loader.LLM_PROMPT_TOKEN_CAP * loader._CHARS_PER_TOKEN
