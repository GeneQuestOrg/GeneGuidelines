"""Initial seed for the rare-disease index.

The 30 entries below mirror exactly the hard-coded list in
:file:`docs/produkty/geneguidelines/draft6/src/views-research.jsx` so the
production autocomplete UX matches the design mock the team approved.
This is *not* the long-term data source — Orphanet's ``en_product1.xml``
will replace this with ~10k entries once the loader (a separate sprint
slice, see :file:`docs/produkty/geneguidelines/plan-f5-update.md`) lands.

Every entry:

- is classified as ``genetic`` and ``is_in_scope=True`` — all 30 are
  Mendelian rare diseases;
- exposes its canonical name, every synonym (PL + EN), every primary gene
  symbol and its OMIM / Orphanet number as a separate alias row, so the
  fuzzy search hits all of them in one round trip;
- pre-fills ``local_slug`` for the four diseases that already have full
  GeneGuidelines content (FD, MAS, Noonan, Marfan), so the autocomplete
  can render the "✓ wytyczne" badge without an extra cross-reference.

``seed_disease_index_if_empty()`` is idempotent and safe to call on every
process start — it bails out as soon as the table has any rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from .models import DiseaseAlias, DiseaseIndexEntry
from .orphanet_loader import (
    build_aliases as _build_orphanet_aliases,
    now_iso,
    parse_disorders,
    parse_gene_associations,
    to_index_entry as _orphanet_to_entry,
)
from .repository import (
    BulkUpsertResult,
    DiseaseIndexRepo,
    SqlaDiseaseIndexRepo,
    normalize_term,
)


SEED_VERSION = "draft6-30entries-2026-05-24"


# --- Source data -------------------------------------------------------------


@dataclass(frozen=True)
class _SeedRecord:
    """Internal shape for the hard-coded seed table.

    Lives here rather than as a JSON file because the dataset is small and
    fully literal — keeping it in Python lets the type checker enforce
    field shapes and we avoid a relative-path round trip at start-up.
    """

    name: str
    omim: str
    orpha: str
    genes: tuple[str, ...]
    synonyms: tuple[str, ...] = ()
    local_slug: str | None = None


_SEED_RECORDS: tuple[_SeedRecord, ...] = (
    # --- diseases that already have full GeneGuidelines content -------------
    _SeedRecord(
        name="Fibrous Dysplasia",
        omim="174800",
        orpha="249",
        genes=("GNAS",),
        synonyms=("FD", "Dysplazja włóknista"),
        local_slug="fd",
    ),
    _SeedRecord(
        name="McCune-Albright Syndrome",
        omim="174800",
        orpha="562",
        genes=("GNAS",),
        synonyms=("MAS", "Zespół McCune-Albrighta"),
        local_slug="mas",
    ),
    _SeedRecord(
        name="Noonan Syndrome",
        omim="163950",
        orpha="648",
        genes=("PTPN11", "SOS1", "RAF1", "KRAS", "RIT1"),
        synonyms=("Zespół Noonana",),
        local_slug="noonan",
    ),
    _SeedRecord(
        name="Marfan Syndrome",
        omim="154700",
        orpha="558",
        genes=("FBN1",),
        synonyms=("Zespół Marfana",),
        local_slug="marfan-syndrome",
    ),
    # --- indexed only — bootstrap workflow runs on demand -------------------
    _SeedRecord(
        name="Bardet-Biedl Syndrome",
        omim="209900",
        orpha="110",
        genes=("BBS1", "BBS2", "BBS10", "MKKS"),
        synonyms=("BBS", "Zespół Bardeta-Biedla"),
    ),
    _SeedRecord(
        name="Wilson Disease",
        omim="277900",
        orpha="905",
        genes=("ATP7B",),
        synonyms=("Choroba Wilsona", "Hepatolenticular degeneration"),
    ),
    _SeedRecord(
        name="Alport Syndrome",
        omim="301050",
        orpha="63",
        genes=("COL4A3", "COL4A4", "COL4A5"),
        synonyms=("Zespół Alporta",),
    ),
    _SeedRecord(
        name="Stargardt Disease",
        omim="248200",
        orpha="827",
        genes=("ABCA4",),
        synonyms=("Choroba Stargardta",),
    ),
    _SeedRecord(
        name="Ehlers-Danlos Syndrome",
        omim="130000",
        orpha="98249",
        genes=("COL5A1", "COL5A2", "COL3A1"),
        synonyms=("EDS", "Zespół Ehlersa-Danlosa"),
    ),
    _SeedRecord(
        name="Fabry Disease",
        omim="301500",
        orpha="324",
        genes=("GLA",),
        synonyms=("Choroba Fabry'ego",),
    ),
    _SeedRecord(
        name="Gaucher Disease",
        omim="230800",
        orpha="355",
        genes=("GBA",),
        synonyms=("Choroba Gauchera",),
    ),
    _SeedRecord(
        name="Pompe Disease",
        omim="232300",
        orpha="365",
        genes=("GAA",),
        synonyms=("Choroba Pompego", "GSD II"),
    ),
    _SeedRecord(
        name="Niemann-Pick Disease",
        omim="257200",
        orpha="77292",
        genes=("SMPD1", "NPC1", "NPC2"),
        synonyms=("NPD", "Choroba Niemanna-Picka"),
    ),
    _SeedRecord(
        name="Rett Syndrome",
        omim="312750",
        orpha="778",
        genes=("MECP2",),
        synonyms=("Zespół Retta",),
    ),
    _SeedRecord(
        name="Angelman Syndrome",
        omim="105830",
        orpha="72",
        genes=("UBE3A",),
        synonyms=("Zespół Angelmana",),
    ),
    _SeedRecord(
        name="Prader-Willi Syndrome",
        omim="176270",
        orpha="739",
        genes=("SNRPN", "NDN"),
        synonyms=("Zespół Pradera-Williego",),
    ),
    _SeedRecord(
        name="Williams Syndrome",
        omim="194050",
        orpha="904",
        genes=("ELN",),
        synonyms=("Zespół Williamsa", "Williams-Beuren"),
    ),
    _SeedRecord(
        name="DiGeorge Syndrome",
        omim="188400",
        orpha="567",
        genes=("TBX1",),
        synonyms=("22q11.2 deletion", "Zespół DiGeorge'a"),
    ),
    _SeedRecord(
        name="Treacher Collins Syndrome",
        omim="154500",
        orpha="861",
        genes=("TCOF1", "POLR1C", "POLR1D"),
        synonyms=("Zespół Treachera Collinsa", "TCS"),
    ),
    _SeedRecord(
        name="Crouzon Syndrome",
        omim="123500",
        orpha="207",
        genes=("FGFR2",),
        synonyms=("Zespół Crouzona",),
    ),
    _SeedRecord(
        name="Apert Syndrome",
        omim="101200",
        orpha="87",
        genes=("FGFR2",),
        synonyms=("Zespół Aperta",),
    ),
    _SeedRecord(
        name="Tuberous Sclerosis Complex",
        omim="191100",
        orpha="805",
        genes=("TSC1", "TSC2"),
        synonyms=("TSC", "Stwardnienie guzowate"),
    ),
    _SeedRecord(
        name="Neurofibromatosis Type 1",
        omim="162200",
        orpha="636",
        genes=("NF1",),
        synonyms=("NF1", "Choroba Recklinghausena"),
    ),
    _SeedRecord(
        name="Neurofibromatosis Type 2",
        omim="101000",
        orpha="637",
        genes=("NF2",),
        synonyms=("NF2",),
    ),
    _SeedRecord(
        name="Hereditary Hemorrhagic Telangiectasia",
        omim="187300",
        orpha="774",
        genes=("ENG", "ACVRL1"),
        synonyms=("HHT", "Osler-Weber-Rendu"),
    ),
    _SeedRecord(
        name="Duchenne Muscular Dystrophy",
        omim="310200",
        orpha="98896",
        genes=("DMD",),
        synonyms=("DMD", "Dystrofia mięśniowa Duchenne'a"),
    ),
    _SeedRecord(
        name="Spinal Muscular Atrophy",
        omim="253300",
        orpha="70",
        genes=("SMN1",),
        synonyms=("SMA", "Rdzeniowy zanik mięśni"),
    ),
    _SeedRecord(
        name="Huntington Disease",
        omim="143100",
        orpha="399",
        genes=("HTT",),
        synonyms=("Choroba Huntingtona",),
    ),
    _SeedRecord(
        name="Friedreich Ataxia",
        omim="229300",
        orpha="95",
        genes=("FXN",),
        synonyms=("Ataksja Friedreicha", "FRDA"),
    ),
    _SeedRecord(
        name="Progeria",
        omim="176670",
        orpha="740",
        genes=("LMNA",),
        synonyms=("HGPS", "Hutchinson-Gilford Progeria Syndrome"),
    ),
    _SeedRecord(
        name="Cri-du-chat Syndrome",
        omim="123450",
        orpha="281",
        genes=(),  # large 5p deletion — no single canonical gene
        synonyms=("Zespół kociego krzyku", "5p- Syndrome"),
    ),
)


# --- Build helpers -----------------------------------------------------------


# Alias kinds get different weights so the same query string ranks the
# canonical name above a synonym above a structured-id match. The exact
# numbers come from the draft6 reference scoring; what matters is the
# strict ordering canonical > synonym > gene > orpha > omim/icd10.
_ALIAS_WEIGHTS: dict[str, float] = {
    "canonical": 1.6,
    "synonym": 1.3,
    "gene": 1.2,
    "orpha": 1.0,
    "omim": 0.9,
    "icd10": 0.8,
    "locale_name": 1.4,
}


def _build_aliases(record: _SeedRecord) -> list[DiseaseAlias]:
    """Generate the alias rows for a seed record.

    Heuristic for ``kind=locale_name`` vs ``kind=synonym``: a synonym
    containing any letter outside ``a-z`` (after Unicode folding) is
    treated as a localised variant. This keeps the alias kinds
    semantically separate so the UI badge can show 🇵🇱 / 🇬🇧 in a future
    iteration if the team wants it.
    """
    aliases: list[DiseaseAlias] = []

    aliases.append(_alias_for(record.name, kind="canonical"))

    seen_norm: set[tuple[str, str]] = {(aliases[0].alias_norm, "canonical")}

    for synonym in record.synonyms:
        kind = "locale_name" if _looks_localised(synonym) else "synonym"
        item = _alias_for(synonym, kind=kind, locale=("pl" if kind == "locale_name" else None))
        key = (item.alias_norm, item.kind)
        if key in seen_norm:
            continue
        seen_norm.add(key)
        aliases.append(item)

    if record.omim:
        aliases.append(_alias_for(record.omim, kind="omim"))
    if record.orpha:
        aliases.append(_alias_for(record.orpha, kind="orpha"))
    for gene in record.genes:
        aliases.append(_alias_for(gene, kind="gene"))

    return aliases


def _alias_for(value: str, *, kind: str, locale: str | None = None) -> DiseaseAlias:
    return DiseaseAlias(
        alias=value.strip(),
        alias_norm=normalize_term(value),
        kind=kind,  # type: ignore[arg-type]
        locale=locale,
        weight=_ALIAS_WEIGHTS.get(kind, 1.0),
    )


def _looks_localised(value: str) -> bool:
    """Cheap heuristic: any non-ASCII letter implies a locale-specific name."""
    return any(ord(ch) > 127 for ch in value)


def _record_to_entry(record: _SeedRecord, *, refreshed_at: str) -> DiseaseIndexEntry:
    return DiseaseIndexEntry(
        primary_id=f"ORPHA:{record.orpha}",
        source="manual",  # promoted to "orphanet" once the XML loader replaces this seed
        canonical_name=record.name,
        canonical_name_norm=normalize_term(record.name),
        category="genetic",
        is_in_scope=True,
        inheritance=None,
        summary="",
        omim_codes=(record.omim,) if record.omim else (),
        gene_symbols=record.genes,
        orpha_url=f"https://www.orpha.net/en/disease/detail/{record.orpha}" if record.orpha else None,
        omim_url=f"https://www.omim.org/entry/{record.omim}" if record.omim else None,
        local_slug=record.local_slug,
        source_version=SEED_VERSION,
        refreshed_at=refreshed_at,
    )


# --- Public seeder -----------------------------------------------------------


def seed_disease_index_if_empty(repo: DiseaseIndexRepo | None = None) -> int:
    """Populate the index from :data:`_SEED_RECORDS` when the table is empty.

    Returns the number of entries written (0 when the table already has
    rows — bail-out is intentional, the seed is *only* a starter). Use the
    Orphanet refresh job for ongoing updates.
    """
    target = repo or SqlaDiseaseIndexRepo()
    if target.count() > 0:
        return 0

    refreshed_at = datetime.now(UTC).isoformat()
    written = 0
    for record in _SEED_RECORDS:
        entry = _record_to_entry(record, refreshed_at=refreshed_at)
        row_id = target.upsert(entry)
        target.replace_aliases(row_id, _build_aliases(record))
        written += 1
    return written


# --- Orphanet bulk import ----------------------------------------------------


@dataclass(frozen=True)
class OrphanetImportResult:
    """Counters returned by :func:`import_orphanet_disorders`."""

    parsed: int           # disorders read from the master XML
    inserted: int         # net new rows in disease_index
    updated: int          # existing non-manual rows refreshed
    skipped_manual: int   # rows preserved because source = 'manual'
    aliases_written: int  # total alias rows replaced for inserted/updated


def import_orphanet_disorders(
    *,
    disorders_xml: str | Path | IO[bytes],
    genes_xml: str | Path | IO[bytes] | None = None,
    source_version: str | None = None,
    repo: SqlaDiseaseIndexRepo | None = None,
    batch_size: int = 500,
) -> OrphanetImportResult:
    """Import every disorder from ``en_product1.xml`` into ``disease_index``.

    Optional ``genes_xml`` (Orphadata's ``en_product6.xml``) adds
    ``gene`` aliases on top. The bulk path uses :class:`BulkUpsertResult`
    so manual-source rows (the 31 hand-curated entries) keep their
    Polish synonyms and ``local_slug`` untouched.

    Idempotent: running the loader twice with the same input is
    equivalent to running it once.
    """
    target = repo or SqlaDiseaseIndexRepo()
    refreshed_at = now_iso()
    version = source_version or f"orphanet-{refreshed_at[:10]}"

    genes_by_orpha: dict[str, tuple[str, ...]] = (
        parse_gene_associations(genes_xml) if genes_xml is not None else {}
    )

    parsed = 0
    inserted = 0
    updated = 0
    skipped_manual = 0
    aliases_written = 0

    # Buffer parsed disorders into batches so the bulk upsert path
    # processes a few hundred rows per round trip — without batching
    # 11k+ disorders the alias REPLACE step becomes a per-row chatter.
    pending_disorders: list = []  # list[OrphanetDisorder]

    def flush(batch: list) -> None:
        nonlocal inserted, updated, skipped_manual, aliases_written
        if not batch:
            return
        entries = [
            _orphanet_to_entry(
                disorder,
                gene_symbols=genes_by_orpha.get(disorder.orpha_code, ()),
                refreshed_at=refreshed_at,
                source_version=version,
            )
            for disorder in batch
        ]
        result: BulkUpsertResult = target.bulk_upsert_orphanet(entries)
        inserted += result.inserted
        updated += result.updated
        skipped_manual += result.skipped_manual

        if result.affected_disease_ids:
            disorder_by_pid = {f"ORPHA:{d.orpha_code}": d for d in batch}
            aliases_by_disease_id: dict[int, list[DiseaseAlias]] = {}
            for disease_id, primary_id in result.affected_disease_ids:
                disorder = disorder_by_pid.get(primary_id)
                if disorder is None:
                    continue
                aliases = _build_orphanet_aliases(
                    disorder,
                    gene_symbols=genes_by_orpha.get(disorder.orpha_code, ()),
                )
                aliases_by_disease_id[disease_id] = aliases
                aliases_written += len(aliases)
            target.bulk_replace_aliases(aliases_by_disease_id)

    for disorder in parse_disorders(disorders_xml):
        if not disorder.orpha_code or not disorder.name:
            continue
        parsed += 1
        pending_disorders.append(disorder)
        if len(pending_disorders) >= batch_size:
            flush(pending_disorders)
            pending_disorders = []
    flush(pending_disorders)

    return OrphanetImportResult(
        parsed=parsed,
        inserted=inserted,
        updated=updated,
        skipped_manual=skipped_manual,
        aliases_written=aliases_written,
    )


__all__ = [
    "SEED_VERSION",
    "seed_disease_index_if_empty",
    "import_orphanet_disorders",
    "OrphanetImportResult",
]
