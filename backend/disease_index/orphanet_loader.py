"""Parse Orphanet's ``en_product1`` (master nomenclature) and
``en_product6`` (gene-disease associations) XML feeds into our
:class:`DiseaseIndexEntry` shape.

Source: ``https://www.orphadata.com/data/xml/`` (Orphadata).
License: Creative Commons Attribution 4.0 (CC-BY-4.0). The ``Source:
Orphanet`` attribution lives in the disease-index entries via
``source = 'orphanet'`` and ``orpha_url`` per row.

Why two files:

- ``en_product1.xml`` — every Orphanet rare disease (~11k as of late
  2025) with name, synonyms, OMIM cross-refs, ICD-10 codes,
  classification metadata. **Mandatory** for the loader; without it
  there is no master list.
- ``en_product6.xml`` — disease-to-gene associations with HGNC gene
  symbols (~5k diseases). **Optional**; if it cannot be loaded the
  master list still ships, just without gene-symbol aliases for the
  Orphanet-imported rows.

Streaming via :func:`xml.etree.ElementTree.iterparse` so a 50 MB feed
parses in <1 GB RAM and we can yield :class:`OrphanetDisorder`
records progressively.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import IO, Iterator, Mapping
from urllib.request import urlopen
from xml.etree import ElementTree

from .models import (
    AliasKind,
    DiseaseAlias,
    DiseaseCategory,
    DiseaseIndexEntry,
)
from .repository import normalize_term
from .scope import is_in_scope


# --- Domain parsing types ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrphanetDisorder:
    """A single Orphanet disorder as parsed from ``en_product1.xml``."""

    orpha_code: str            # "249" (no prefix)
    name: str                  # canonical English name
    synonyms: tuple[str, ...] = ()
    omim_codes: tuple[str, ...] = ()
    icd10_codes: tuple[str, ...] = ()
    disorder_type: str = ""    # "Disease", "Group of disorders", "Subtype of disorder", …
    disorder_group: str = ""   # "Disorder", "Phenome", "Group of disorders"


@dataclass(frozen=True, slots=True)
class OrphanetGeneAssociation:
    """Parsed gene association from ``en_product6.xml``."""

    orpha_code: str
    gene_symbols: tuple[str, ...] = ()


# --- Static classification overrides ----------------------------------------
#
# Orphanet's master nomenclature does not classify a disorder as "genetic
# vs infectious vs acquired". The full classification lives in separate
# ``en_product3_*.xml`` files, one per branch of the Orphanet tree —
# loading them is a heavier lift and not blocking the autocomplete UX.
#
# Default classification: every imported disorder is treated as
# ``genetic`` (the platform's primary editorial scope). The small map
# below carries the obvious exceptions so the autocomplete renders the
# correct out-of-scope badge for diseases parents may still type.
#
# This list is deliberately short — the Tier 2 Gemma classifier handles
# the long tail at search time. Add high-traffic exceptions here once
# they show up in production logs.
_NON_GENETIC_OVERRIDES: dict[str, DiseaseCategory] = {
    # Rare infectious diseases (subset of ORPHA:557492 tree).
    "3389": "infectious",   # Tuberculosis
    "264580": "infectious",  # SARS — severe acute respiratory syndrome
    "636": "infectious",    # Mycobacteriosis
    # Rare allergic / multifactorial — examples that show up in queries.
    "139": "multifactorial",  # Acquired idiopathic generalized anhidrosis
}


_OMIM_NUMERIC_RE = "0123456789"


# --- Master-list parser (en_product1.xml) -----------------------------------


def parse_disorders(source: str | Path | IO[bytes]) -> Iterator[OrphanetDisorder]:
    """Iterate :class:`OrphanetDisorder` records from ``en_product1.xml``.

    ``source`` may be a URL (``http://`` / ``https://``), a filesystem
    path, or an open binary file-like object — the loader normalises
    them via :func:`_open_xml`. The parser uses ``iterparse`` so memory
    stays bounded regardless of input size.
    """
    with _open_xml(source) as fp:
        for elem in _iter_disorder_elems(fp):
            yield _disorder_from_element(elem)
            elem.clear()


def _iter_disorder_elems(fp: IO[bytes]) -> Iterator[ElementTree.Element]:
    context = ElementTree.iterparse(fp, events=("end",))
    for event, elem in context:
        if event == "end" and elem.tag == "Disorder":
            yield elem


def _disorder_from_element(elem: ElementTree.Element) -> OrphanetDisorder:
    orpha_code = (elem.findtext("OrphaCode") or "").strip()
    name = (elem.findtext("Name") or "").strip()

    synonyms: list[str] = []
    for synonym in elem.findall("SynonymList/Synonym"):
        text = (synonym.text or "").strip()
        if text:
            synonyms.append(text)

    omim_codes: list[str] = []
    icd10_codes: list[str] = []
    for ref in elem.findall("ExternalReferenceList/ExternalReference"):
        source = (ref.findtext("Source") or "").strip()
        reference = (ref.findtext("Reference") or "").strip()
        if not source or not reference:
            continue
        if source == "OMIM":
            # Orphanet ships OMIM phenotype numbers as plain digits.
            cleaned = "".join(ch for ch in reference if ch in _OMIM_NUMERIC_RE)
            if cleaned:
                omim_codes.append(cleaned)
        elif source == "ICD-10":
            icd10_codes.append(reference)

    disorder_type = (elem.findtext("DisorderType/Name") or "").strip()
    disorder_group = (elem.findtext("DisorderGroup/Name") or "").strip()

    return OrphanetDisorder(
        orpha_code=orpha_code,
        name=name,
        synonyms=tuple(dict.fromkeys(synonyms)),  # de-dup, preserve order
        omim_codes=tuple(dict.fromkeys(omim_codes)),
        icd10_codes=tuple(dict.fromkeys(icd10_codes)),
        disorder_type=disorder_type,
        disorder_group=disorder_group,
    )


# --- Gene-association parser (en_product6.xml) ------------------------------


def parse_gene_associations(
    source: str | Path | IO[bytes],
) -> dict[str, tuple[str, ...]]:
    """Return ``{orpha_code: (gene_symbol, …)}`` from ``en_product6.xml``.

    Each disorder in the file may have several gene associations; we
    flatten them and de-duplicate symbols while preserving discovery
    order (so the canonical / first-known gene comes first in the
    autocomplete chips).
    """
    result: dict[str, list[str]] = {}
    with _open_xml(source) as fp:
        context = ElementTree.iterparse(fp, events=("end",))
        for event, elem in context:
            if event != "end" or elem.tag != "Disorder":
                continue
            orpha_code = (elem.findtext("OrphaCode") or "").strip()
            if not orpha_code:
                elem.clear()
                continue
            symbols: list[str] = []
            for assoc in elem.findall(
                "DisorderGeneAssociationList/DisorderGeneAssociation/Gene"
            ):
                symbol = (assoc.findtext("Symbol") or "").strip()
                if symbol and symbol not in symbols:
                    symbols.append(symbol)
            if symbols:
                result.setdefault(orpha_code, []).extend(symbols)
                # Deduplicate after merging (rare, but the same gene can
                # appear under both germline and somatic associations).
                result[orpha_code] = list(dict.fromkeys(result[orpha_code]))
            elem.clear()
    return {orpha: tuple(symbols) for orpha, symbols in result.items()}


# --- Transformation to DiseaseIndexEntry ------------------------------------


@dataclass(frozen=True, slots=True)
class _AliasWeight:
    canonical: float = 1.6
    synonym: float = 1.3
    omim: float = 0.9
    orpha: float = 1.0
    icd10: float = 0.8
    gene: float = 1.2


_DEFAULT_WEIGHTS = _AliasWeight()


def to_index_entry(
    disorder: OrphanetDisorder,
    *,
    gene_symbols: tuple[str, ...] = (),
    refreshed_at: str,
    source_version: str,
) -> DiseaseIndexEntry:
    """Map a parsed :class:`OrphanetDisorder` onto a domain entry.

    ``gene_symbols`` is supplied by the gene-association parser (or
    empty when ``en_product6.xml`` is not available). ``inheritance``
    and ``summary`` stay empty — Orphadata's master nomenclature does
    not carry them, and pulling them from the per-disorder Orphanet
    page would require either a third XML file or scraping (deferred).
    """
    primary_id = f"ORPHA:{disorder.orpha_code}"
    category: DiseaseCategory = _NON_GENETIC_OVERRIDES.get(
        disorder.orpha_code, "genetic"
    )
    return DiseaseIndexEntry(
        primary_id=primary_id,
        source="orphanet",
        canonical_name=disorder.name,
        canonical_name_norm=normalize_term(disorder.name),
        category=category,
        is_in_scope=is_in_scope(category),
        inheritance=None,
        summary="",
        omim_codes=disorder.omim_codes,
        gene_symbols=gene_symbols,
        orpha_url=f"https://www.orpha.net/en/disease/detail/{disorder.orpha_code}",
        omim_url=(
            f"https://www.omim.org/entry/{disorder.omim_codes[0]}"
            if disorder.omim_codes
            else None
        ),
        local_slug=None,
        source_version=source_version,
        refreshed_at=refreshed_at,
    )


def build_aliases(
    disorder: OrphanetDisorder,
    *,
    gene_symbols: tuple[str, ...] = (),
    weights: _AliasWeight = _DEFAULT_WEIGHTS,
) -> list[DiseaseAlias]:
    """Produce alias rows for a disorder.

    The alias *kind* drives the score bonus at query time
    (:func:`backend.disease_index.repository.score_match`), so getting
    the kinds right matters for ranking even when the search term
    looks identical (e.g. typing ``174800`` should rank an ``omim``
    alias above a same-string ``synonym``).
    """
    aliases: list[DiseaseAlias] = []
    seen: set[tuple[str, str]] = set()

    def add(alias: str, kind: AliasKind, weight: float, locale: str | None = None) -> None:
        text = alias.strip()
        if not text:
            return
        norm = normalize_term(text)
        if not norm:
            return
        key = (norm, kind)
        if key in seen:
            return
        seen.add(key)
        aliases.append(
            DiseaseAlias(
                alias=text,
                alias_norm=norm,
                kind=kind,
                locale=locale,
                weight=weight,
            )
        )

    if disorder.name:
        add(disorder.name, "canonical", weights.canonical, "en")
    for synonym in disorder.synonyms:
        add(synonym, "synonym", weights.synonym, "en")
    if disorder.orpha_code:
        add(disorder.orpha_code, "orpha", weights.orpha)
    for omim in disorder.omim_codes:
        add(omim, "omim", weights.omim)
    for icd10 in disorder.icd10_codes:
        add(icd10, "icd10", weights.icd10)
    for gene in gene_symbols:
        add(gene, "gene", weights.gene)

    return aliases


# --- IO helpers -------------------------------------------------------------


def _open_xml(source: str | Path | IO[bytes]):
    """Return a binary file-like pointing at ``source``.

    Three input modes:
    - URL string (``http://`` / ``https://``) — opened with urllib;
    - filesystem path — opened in binary mode;
    - already-open binary file-like — wrapped in a no-op closer so
      callers in the test suite can pass ``BytesIO`` directly.
    """
    if isinstance(source, (str, Path)):
        text = str(source)
        if text.startswith(("http://", "https://")):
            return urlopen(text, timeout=120)  # noqa: S310 — Orphadata is HTTPS
        return open(text, "rb")
    return _NoOpCloser(source)


class _NoOpCloser:
    """Adapter so an open BytesIO behaves like a context manager."""

    def __init__(self, fp: IO[bytes]) -> None:
        self._fp = fp

    def __enter__(self) -> IO[bytes]:
        return self._fp

    def __exit__(self, *_) -> None:  # noqa: ANN401 — context-manager protocol
        return None


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


__all__ = [
    "OrphanetDisorder",
    "OrphanetGeneAssociation",
    "parse_disorders",
    "parse_gene_associations",
    "to_index_entry",
    "build_aliases",
    "now_iso",
]
