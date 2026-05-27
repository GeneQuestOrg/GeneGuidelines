"""Domain models for the rare-disease index.

Pure ``@dataclass(frozen=True, slots=True)`` value objects, mirroring the
shape used in :mod:`backend.content.models`. The authoritative input/output
shapes are Pydantic DTOs in :mod:`backend.disease_index.contracts`; this
module never imports Pydantic.

Why split entries from aliases:
- An entry is one rare disease (one ORPHA / OMIM / MONDO id).
- A rare disease has many *aliases* — canonical name in EN/PL/FR, common
  abbreviations (FD, BBS), gene symbols (FBN1), OMIM and ORPHA codes.
  Each alias is a searchable handle; storing them separately lets a single
  fuzzy index hit the lot in one round trip.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal, Mapping


# --- Constants ---------------------------------------------------------------

#: How a disease maps onto GeneGuidelines' editorial scope. Drives the
#: ``is_in_scope`` boolean and the UI badge ("Run research" vs "Out of scope").
DiseaseCategory = Literal[
    "genetic",                # canonical Mendelian disease — fully in scope
    "predominantly_genetic",  # mostly genetic, may have environmental modifier
    "multifactorial",         # complex, mixed genetic + environmental
    "infectious",             # caused by a pathogen — out of scope
    "acquired",               # sporadic / acquired — out of scope
    "unknown",                # classifier could not place it confidently
]

#: Where an entry came from. Drives the source badge in the autocomplete UI.
DiseaseIndexSource = Literal["orphanet", "mondo", "gard", "manual"]

#: Why a particular alias is searchable.
AliasKind = Literal[
    "canonical",     # the canonical English name
    "synonym",       # alternative spelling / older nomenclature
    "omim",          # OMIM phenotype number
    "gene",          # HGNC gene symbol
    "orpha",         # Orphanet number
    "icd10",         # ICD-10 code
    "locale_name",   # canonical name in a non-English locale
]


# --- Dataclasses -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DiseaseAlias:
    """A single searchable handle for a :class:`DiseaseIndexEntry`."""

    alias: str
    alias_norm: str
    kind: AliasKind
    locale: str | None = None
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class DiseaseIndexEntry:
    """A single row of the global rare-disease index.

    Aliases are populated when the repository returns the entry from a
    search; for plain ``get`` calls the tuple may be empty unless the
    caller explicitly asked for ``with_aliases=True``.
    """

    primary_id: str           # e.g. "ORPHA:558"
    source: DiseaseIndexSource
    canonical_name: str
    canonical_name_norm: str
    category: DiseaseCategory | None
    is_in_scope: bool
    inheritance: str | None
    summary: str
    omim_codes: tuple[str, ...] = field(default_factory=tuple)
    gene_symbols: tuple[str, ...] = field(default_factory=tuple)
    orpha_url: str | None = None
    omim_url: str | None = None
    local_slug: str | None = None
    source_version: str | None = None
    refreshed_at: str = ""
    aliases: tuple[DiseaseAlias, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DiseaseSuggestion:
    """A ranked candidate returned by :class:`service.DiseaseSuggestionService`.

    Wraps the underlying :class:`DiseaseIndexEntry` together with the alias
    that actually matched the query and the composite score that drives the
    sort order. ``has_local_record`` is computed at the service layer by
    cross-referencing :class:`backend.content.repository.DiseaseRepo`.
    """

    entry: DiseaseIndexEntry
    matched_alias: DiseaseAlias
    score: float                # 0..∞ — higher = better match
    has_local_record: bool      # we already have full content for this disease


# --- Row mappers -------------------------------------------------------------


def entry_from_row(
    row: Mapping[str, object],
    *,
    aliases: tuple[DiseaseAlias, ...] = (),
) -> DiseaseIndexEntry:
    """Map a ``disease_index`` row to a :class:`DiseaseIndexEntry`."""

    return DiseaseIndexEntry(
        primary_id=str(row["primary_id"]),
        source=str(row["source"]),  # type: ignore[arg-type]
        canonical_name=str(row["canonical_name"]),
        canonical_name_norm=str(row["canonical_name_norm"]),
        category=_nullable_str(row.get("category")),  # type: ignore[arg-type]
        is_in_scope=bool(row["is_in_scope"]),
        inheritance=_nullable_str(row.get("inheritance")),
        summary=str(row.get("summary") or ""),
        omim_codes=_decode_str_tuple(row.get("omim_codes_json")),
        gene_symbols=_decode_str_tuple(row.get("gene_symbols_json")),
        orpha_url=_nullable_str(row.get("orpha_url")),
        omim_url=_nullable_str(row.get("omim_url")),
        local_slug=_nullable_str(row.get("local_slug")),
        source_version=_nullable_str(row.get("source_version")),
        refreshed_at=str(row.get("refreshed_at") or ""),
        aliases=aliases,
    )


def alias_from_row(row: Mapping[str, object]) -> DiseaseAlias:
    """Map a ``disease_index_aliases`` row to a :class:`DiseaseAlias`."""

    return DiseaseAlias(
        alias=str(row["alias"]),
        alias_norm=str(row["alias_norm"]),
        kind=str(row["kind"]),  # type: ignore[arg-type]
        locale=_nullable_str(row.get("locale")),
        weight=float(row.get("weight") or 1.0),
    )


# --- Helpers -----------------------------------------------------------------


def _nullable_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return str(value)


def _decode_str_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, str) or not value.strip():
        return ()
    try:
        items = json.loads(value)
    except json.JSONDecodeError:
        return ()
    return tuple(str(s) for s in items if isinstance(s, str))


__all__ = [
    "DiseaseCategory",
    "DiseaseIndexSource",
    "AliasKind",
    "DiseaseAlias",
    "DiseaseIndexEntry",
    "DiseaseSuggestion",
    "entry_from_row",
    "alias_from_row",
]
