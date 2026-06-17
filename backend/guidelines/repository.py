"""Repository for the guidelines layer — Protocol + ORM + in-memory.

Port/adapter idiom (like ``account`` / ``doctor_contributions``): the service
depends on the :class:`GuidelinesRepo` Protocol (read surface). The production
:class:`SqlaGuidelinesRepo` is ORM (``Session`` per call) and additionally
carries the bulk-insert helpers the seed loader uses. :class:`InMemoryGuidelinesRepo`
is a dict-backed fake for service/API tests.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from ..shared.persistence.engine import get_engine
from .models import (
    GuidelineSuggestion,
    GuidelineSynthesis,
    SourceDocument,
    SynthSectionSignal,
)
from .orm import (
    GuidelineSuggestionRow,
    GuidelineSynthesisRow,
    GuidelineSynthesisSignalRow,
    SourceDocumentRow,
)


# ---------------------------------------------------------------------------
# Row -> domain mappers.
# ---------------------------------------------------------------------------


def source_document_from_row(row: SourceDocumentRow) -> SourceDocument:
    return SourceDocument(
        disease_slug=row.disease_slug,
        doc_id=row.doc_id,
        role=row.role,
        title=row.title,
        authors=row.authors,
        journal=row.journal,
        year=row.year,
        scope=row.scope,
        covers=list(row.covers or []),
        pmid=row.pmid,
        bookshelf=row.bookshelf,
        free_full_text=bool(row.free_full_text),
        is_new=bool(row.is_new),
        updates_note=row.updates_note,
    )


def synthesis_from_row(row: GuidelineSynthesisRow) -> GuidelineSynthesis:
    return GuidelineSynthesis(
        disease_slug=row.disease_slug,
        kind=row.kind,
        title=row.title,
        version=row.version,
        last_updated=row.last_updated,
        based_on=row.based_on,
        synth_disclaimer=row.synth_disclaimer,
        status=row.status,
        epistemic_level=row.epistemic_level,
        has_flowchart=bool(row.has_flowchart),
        source_ids=list(row.source_ids or []),
        sections=list(row.sections or []),
        what_to_do_now=row.what_to_do_now,
        red_flags=row.red_flags,
    )


def suggestion_from_row(row: GuidelineSuggestionRow) -> GuidelineSuggestion:
    return GuidelineSuggestion(
        disease_slug=row.disease_slug,
        id=row.id,
        kind=row.kind,
        target_section=row.target_section,
        section_label=row.section_label,
        title=row.title,
        summary=row.summary,
        rationale=row.rationale,
        evidence=row.evidence,
        gate=row.gate,
        citations=list(row.citations or []),
        signal=dict(row.signal or {}),
        comments=list(row.comments or []),
        parent_text=row.parent_text,
        diff=row.diff,
        regen_seed=row.regen_seed,
    )


def signal_from_row(row: GuidelineSynthesisSignalRow) -> SynthSectionSignal:
    return SynthSectionSignal(
        section_id=row.section_id,
        up=row.up,
        flags=row.flags,
        verified=row.verified,
        flag_notes=row.flag_notes,
    )


class GuidelinesRepo(Protocol):
    """Port — the read surface :class:`GuidelinesService` depends on."""

    def list_source_documents(self, disease_slug: str) -> list[SourceDocument]: ...
    def get_synthesis(self, disease_slug: str) -> GuidelineSynthesis | None: ...
    def list_suggestions(self, disease_slug: str) -> list[GuidelineSuggestion]: ...
    def get_synthesis_signals(
        self, disease_slug: str
    ) -> dict[str, SynthSectionSignal]: ...


class SqlaGuidelinesRepo:
    """Production ORM impl — ``Session`` per operation against the shared engine."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()

    # -- reads --------------------------------------------------------------

    def list_source_documents(self, disease_slug: str) -> list[SourceDocument]:
        stmt = (
            select(SourceDocumentRow)
            .where(SourceDocumentRow.disease_slug == disease_slug)
            .order_by(SourceDocumentRow.sort_order, SourceDocumentRow.doc_id)
        )
        with Session(self._engine) as session:
            return [source_document_from_row(r) for r in session.scalars(stmt)]

    def get_synthesis(self, disease_slug: str) -> GuidelineSynthesis | None:
        with Session(self._engine) as session:
            row = session.get(GuidelineSynthesisRow, disease_slug)
            return synthesis_from_row(row) if row is not None else None

    def list_suggestions(self, disease_slug: str) -> list[GuidelineSuggestion]:
        stmt = (
            select(GuidelineSuggestionRow)
            .where(GuidelineSuggestionRow.disease_slug == disease_slug)
            .order_by(GuidelineSuggestionRow.sort_order, GuidelineSuggestionRow.id)
        )
        with Session(self._engine) as session:
            return [suggestion_from_row(r) for r in session.scalars(stmt)]

    def get_synthesis_signals(
        self, disease_slug: str
    ) -> dict[str, SynthSectionSignal]:
        stmt = select(GuidelineSynthesisSignalRow).where(
            GuidelineSynthesisSignalRow.disease_slug == disease_slug
        )
        with Session(self._engine) as session:
            return {
                r.section_id: signal_from_row(r) for r in session.scalars(stmt)
            }

    # -- seed-time writes (not on the Protocol; used by seed.py) ------------

    def has_any_synthesis(self) -> bool:
        with Session(self._engine) as session:
            return session.query(GuidelineSynthesisRow).first() is not None

    def insert_source_document(self, disease_slug: str, doc: dict, sort_order: int) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(
                SourceDocumentRow(
                    disease_slug=disease_slug,
                    doc_id=doc["id"],
                    role=doc["role"],
                    title=doc["title"],
                    authors=doc["authors"],
                    journal=doc["journal"],
                    year=str(doc["year"]),
                    scope=doc["scope"],
                    covers=list(doc.get("covers", [])),
                    sort_order=sort_order,
                    pmid=doc.get("pmid"),
                    bookshelf=doc.get("bookshelf"),
                    free_full_text=1 if doc.get("freeFullText") else 0,
                    is_new=1 if doc.get("isNew") else 0,
                    updates_note=doc.get("updatesNote"),
                )
            )

    def upsert_synthesis(self, disease_slug: str, syn: dict) -> None:
        """Insert-or-replace the single synthesis row for ``disease_slug``.

        The synthesis table is keyed on ``disease_slug`` alone, so a re-run
        (the generation engine writing fresh output) must overwrite — not
        collide on the primary key. Delete-then-add in one transaction; the
        ``delete()`` statement emits its SQL before the ``add`` flushes on
        commit, so there is no insert-before-delete ordering hazard.
        """
        with Session(self._engine) as session, session.begin():
            session.execute(
                delete(GuidelineSynthesisRow).where(
                    GuidelineSynthesisRow.disease_slug == disease_slug
                )
            )
            session.add(
                GuidelineSynthesisRow(
                    disease_slug=disease_slug,
                    title=syn["title"],
                    version=syn["version"],
                    last_updated=syn["lastUpdated"],
                    based_on=syn["basedOn"],
                    synth_disclaimer=syn["synthDisclaimer"],
                    status=syn["status"],
                    epistemic_level=syn.get("epistemicLevel", "a"),
                    kind=syn.get("kind", "synthesis"),
                    has_flowchart=1 if syn.get("hasFlowchart") else 0,
                    source_ids=list(syn.get("sourceIds", [])),
                    sections=list(syn.get("sections", [])),
                    what_to_do_now=syn.get("whatToDoNow"),
                    red_flags=syn.get("redFlags"),
                )
            )

    def insert_suggestion(self, disease_slug: str, sug: dict, sort_order: int) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(
                GuidelineSuggestionRow(
                    disease_slug=disease_slug,
                    id=sug["id"],
                    kind=sug["kind"],
                    target_section=sug["targetSection"],
                    section_label=sug["sectionLabel"],
                    title=sug["title"],
                    summary=sug["summary"],
                    rationale=sug["rationale"],
                    evidence=sug["evidence"],
                    gate=sug["gate"],
                    citations=list(sug.get("citations", [])),
                    signal=dict(sug.get("signal", {})),
                    comments=list(sug.get("comments", [])),
                    sort_order=sort_order,
                    parent_text=sug.get("parentText"),
                    diff=sug.get("diff"),
                    regen_seed=sug.get("regenSeed"),
                )
            )

    def replace_suggestions(self, disease_slug: str, suggestions: list[dict]) -> None:
        """Replace all suggestions for ``disease_slug`` (delete by slug + bulk insert).

        The generation engine (level b) re-derives the full delta set each run,
        so old rows for this disease are cleared first; ``sort_order`` follows
        list order. One transaction.
        """
        with Session(self._engine) as session, session.begin():
            session.execute(
                delete(GuidelineSuggestionRow).where(
                    GuidelineSuggestionRow.disease_slug == disease_slug
                )
            )
            for sort_order, sug in enumerate(suggestions):
                session.add(
                    GuidelineSuggestionRow(
                        disease_slug=disease_slug,
                        id=sug["id"],
                        kind=sug["kind"],
                        target_section=sug["targetSection"],
                        section_label=sug["sectionLabel"],
                        title=sug["title"],
                        summary=sug["summary"],
                        rationale=sug["rationale"],
                        evidence=sug["evidence"],
                        gate=sug["gate"],
                        citations=list(sug.get("citations", [])),
                        signal=dict(sug.get("signal", {})),
                        comments=list(sug.get("comments", [])),
                        sort_order=sort_order,
                        parent_text=sug.get("parentText"),
                        diff=sug.get("diff"),
                        regen_seed=sug.get("regenSeed"),
                    )
                )

    def upsert_synthesis_signal(
        self, disease_slug: str, section_id: str, sig: dict
    ) -> None:
        with Session(self._engine) as session, session.begin():
            session.add(
                GuidelineSynthesisSignalRow(
                    disease_slug=disease_slug,
                    section_id=section_id,
                    up=int(sig.get("up", 0)),
                    flags=int(sig.get("flags", 0)),
                    verified=int(sig.get("verified", 0)),
                    flag_notes=sig.get("flagNotes"),
                )
            )


class InMemoryGuidelinesRepo:
    """Dict-backed fake for service/API tests (and DB-less dev)."""

    def __init__(self) -> None:
        self.source_documents: dict[str, list[SourceDocument]] = {}
        self.synthesis: dict[str, GuidelineSynthesis] = {}
        self.suggestions: dict[str, list[GuidelineSuggestion]] = {}
        self.signals: dict[str, dict[str, SynthSectionSignal]] = {}

    def list_source_documents(self, disease_slug: str) -> list[SourceDocument]:
        return list(self.source_documents.get(disease_slug, []))

    def get_synthesis(self, disease_slug: str) -> GuidelineSynthesis | None:
        return self.synthesis.get(disease_slug)

    def list_suggestions(self, disease_slug: str) -> list[GuidelineSuggestion]:
        return list(self.suggestions.get(disease_slug, []))

    def get_synthesis_signals(
        self, disease_slug: str
    ) -> dict[str, SynthSectionSignal]:
        return dict(self.signals.get(disease_slug, {}))


__all__ = [
    "GuidelinesRepo",
    "SqlaGuidelinesRepo",
    "InMemoryGuidelinesRepo",
    "source_document_from_row",
    "synthesis_from_row",
    "suggestion_from_row",
    "signal_from_row",
]
