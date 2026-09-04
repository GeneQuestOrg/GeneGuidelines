"""Open-access full text for shelf documents, via Europe PMC.

Why this module exists. The guideline synthesis used to be written from PubMed
*abstracts* alone, and the output read like an encyclopedia entry rather than a
guideline — because the input was one. Concretely, for the FD/MAS consensus
(PMID 31196103) the abstract is 3.9 kB and contains **zero** occurrences of
"biopsy", "histolog", "scintigraph" or "radiograph"; the open-access full text is
166 kB and says, in the "Histological and genetic characterisation" section:

    "Biopsy with histological evaluation of suspected bone disease is usually only
    necessary in unusual or questionable cases, and/or if malignancy is suspected."

That sentence is the single most useful thing the guideline has to say to a family
facing a proposed operation, and no model could have produced it from the abstract.
Asking for it from an abstract would have been asking for a hallucination.

Europe PMC serves the full text as JATS XML for open-access articles, keyed by
PMCID, with no API key. We resolve PMID → PMCID through NCBI elink, then fetch and
flatten the XML to section-tagged plain text so a prompt can carry
"section: sentence" provenance rather than just a PMID.

Everything here is best-effort: no PMCID, a closed-access article, or a failing
request degrades to the abstract, which is what the pipeline did before. Never
raise into the flow.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import httpx

log = logging.getLogger(__name__)

_ELINK = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
_EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
_TIMEOUT = 30.0

# Sections that carry clinical guidance. The reference list, competing interests
# and acknowledgements are pure noise in a prompt and would crowd out real content
# under the token cap.
_SKIP_SECTION_RE = re.compile(
    r"^(references?|bibliograph|acknowledge?ments?|competing interests|"
    r"conflicts? of interest|author.?s? contributions?|funding|"
    r"abbreviations|supplementary|additional file|ethics|consent|"
    r"publisher.?s note|about this article)",
    re.I,
)


def _pmid_to_pmcid(pmids: list[str], api_key: str | None = None) -> dict[str, str]:
    """PMID → PMCID for the ones that have an open-access record. Soft-fails to {}."""
    if not pmids:
        return {}
    # Two elink traps, both hit while building this:
    #  1. A comma-joined `id=` returns ONE merged linkset for every input, so the
    #     PMID→PMCID pairing is lost. Repeated `id=` params return one linkset per
    #     input id, which is what we need.
    #  2. Each linkset carries several linksetdbs. `pubmed_pmc` is the article's own
    #     PMC record; `pubmed_pmc_refs` is the ~150 articles that CITE it. Taking the
    #     first linksetdb silently returned a citing paper — for the FD consensus it
    #     yielded PMC11087144 (a different 2023 review) instead of PMC6567644.
    params: list[tuple[str, str]] = [
        ("dbfrom", "pubmed"),
        ("db", "pmc"),
        ("linkname", "pubmed_pmc"),
        ("retmode", "json"),
    ]
    params.extend(("id", pmid) for pmid in pmids)
    if api_key:
        params.append(("api_key", api_key))
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.get(_ELINK, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — full text is an upgrade, never a dependency
        log.warning("pmc_fulltext: elink failed: %s", exc)
        return {}

    out: dict[str, str] = {}
    for idx, linkset in enumerate(payload.get("linksets") or []):
        ids = linkset.get("ids") or []
        pmid = str(ids[0]) if ids else (pmids[idx] if idx < len(pmids) else "")
        for db in linkset.get("linksetdbs") or []:
            if db.get("linkname") != "pubmed_pmc":
                continue
            links = db.get("links") or []
            if links:
                out[str(pmid)] = f"PMC{links[0]}"
            break
    return out


def _section_title(sec: ET.Element) -> str:
    title = sec.find("title")
    if title is None:
        return ""
    return " ".join("".join(title.itertext()).split())


def _flatten_section(sec: ET.Element, inherited: str = "") -> list[tuple[str, str]]:
    """(section title, paragraph text) pairs, recursing into nested <sec>."""
    title = _section_title(sec) or inherited
    if _SKIP_SECTION_RE.match(title):
        return []

    out: list[tuple[str, str]] = []
    for child in sec:
        if child.tag == "sec":
            out.extend(_flatten_section(child, title))
        elif child.tag in ("p", "list", "table-wrap", "fig"):
            # Figure and table captions matter here: the scintigraphy evidence in
            # the FD consensus lives in a figure caption, not in body prose.
            text = " ".join("".join(child.itertext()).split())
            if len(text) >= 40:
                out.append((title, text))
    return out


def _fetch_xml(pmcid: str, api_key: str | None = None) -> str:
    """Article XML from Europe PMC, falling back to NCBI efetch.

    The two sources do not carry the same articles. Europe PMC 404s on records it
    has not ingested into its open-access subset — including PMC11087144, the 2023
    craniofacial FD review, which NCBI serves in full (77 kB with a <body>). Before
    this fallback existed that paper contributed nothing but its abstract, which is
    why every synthesised paragraph but one came from the consensus document.

    Returns "" when neither source has a body to give (some PMC deposits really are
    abstract-only — PMC7127130 is one).
    """
    attempts = [
        (f"{_EUROPE_PMC}/{pmcid}/fullTextXML", None),
        (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            {"db": "pmc", "id": pmcid.removeprefix("PMC"), "rettype": "xml", "retmode": "xml"}
            | ({"api_key": api_key} if api_key else {}),
        ),
    ]
    for url, params in attempts:
        try:
            with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url, params=params)
            if resp.status_code != 200 or not resp.text.lstrip().startswith("<"):
                continue
            if "<body" not in resp.text:
                continue  # abstract-only deposit; try the next source
            return resp.text
        except Exception as exc:  # noqa: BLE001
            log.info("pmc_fulltext: %s failed for %s: %s", url, pmcid, exc)
    return ""


def fetch_fulltext_sections(
    pmid: str, pmcid: str, api_key: str | None = None
) -> list[tuple[str, str]]:
    """Section-tagged paragraphs of an open-access article. [] when unavailable."""
    xml = _fetch_xml(pmcid, api_key=api_key)
    if not xml:
        log.info("pmc_fulltext: no full text for %s (%s)", pmid, pmcid)
        return []
    try:
        root = ET.fromstring(xml)
    except Exception as exc:  # noqa: BLE001
        log.info("pmc_fulltext: unparseable XML for %s (%s): %s", pmid, pmcid, exc)
        return []

    body = root.find(".//body")
    if body is None:
        return []

    out: list[tuple[str, str]] = []
    for sec in body.findall("sec"):
        out.extend(_flatten_section(sec))
    if not out:
        # Some deposits put paragraphs straight in <body> with no <sec> wrapper.
        for para in body.findall("p"):
            text = " ".join("".join(para.itertext()).split())
            if len(text) >= 40:
                out.append(("", text))
    return out


def render_for_prompt(sections: list[tuple[str, str]], char_budget: int) -> str:
    """Section-labelled text for a prompt, truncated at a whole paragraph.

    Labels are kept so a paragraph can cite "section: X" and the reader can find
    the claim in the source document — the per-claim provenance the vision asks
    for (wizja/04-silnik-wiedzy.md, "Provenance per twierdzenie").
    """
    chunks: list[str] = []
    used = 0
    last_title = None
    for title, text in sections:
        piece = (f"\n### {title}\n" if title and title != last_title else "") + text
        if used + len(piece) > char_budget:
            break
        chunks.append(piece)
        used += len(piece)
        last_title = title or last_title
    return "\n".join(chunks).strip()


def fetch_fulltext_by_pmid(
    pmids: list[str], *, char_budget: int, api_key: str | None = None
) -> dict[str, str]:
    """PMID → prompt-ready full text, for the articles that have one.

    Absent keys mean "no open-access full text" and the caller should fall back to
    the abstract. ``char_budget`` is per article, so the shelf as a whole stays
    inside LLM_PROMPT_TOKEN_CAP.
    """
    pmcid_by_pmid = _pmid_to_pmcid(pmids, api_key=api_key)
    out: dict[str, str] = {}
    for pmid, pmcid in pmcid_by_pmid.items():
        sections = fetch_fulltext_sections(pmid, pmcid, api_key=api_key)
        if not sections:
            continue
        rendered = render_for_prompt(sections, char_budget)
        if rendered:
            out[pmid] = rendered
    return out


def pmc_url(pmcid: str) -> str:
    return f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"


__all__ = [
    "fetch_fulltext_by_pmid",
    "fetch_fulltext_sections",
    "render_for_prompt",
    "pmc_url",
    "_pmid_to_pmcid",
]
