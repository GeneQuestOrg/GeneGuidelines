"""Repository for the guidelines layer — Protocol + ORM + in-memory.

Port/adapter idiom (like ``account`` / ``doctor_contributions``): the service
depends on the :class:`GuidelinesRepo` Protocol (read surface). The production
:class:`SqlaGuidelinesRepo` is ORM (``Session`` per call) and additionally
carries the bulk-insert helpers the seed loader uses. :class:`InMemoryGuidelinesRepo`
is a dict-backed fake for service/API tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from ..shared.persistence.engine import get_engine
from .models import (
    GuidelineSuggestion,
    GuidelineSynthesis,
    GuidelineSynthesisTranslation,
    SourceDocument,
    SynthSectionSignal,
)
from .orm import (
    GuidelineSuggestionRow,
    GuidelineSuggestionVoteRow,
    GuidelineSynthesisRow,
    GuidelineSynthesisSignalRow,
    GuidelineSynthesisTranslationRow,
    SourceDocumentRow,
)

# Verdicts a clinician can leave on a suggestion (frontend ``Rating`` type).
SUGGESTION_VERDICTS: frozenset[str] = frozenset({"useful", "not", "wrong"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_signal() -> dict[str, int]:
    return {"useful": 0, "not": 0, "wrong": 0, "ratings": 0, "verified": 0}


def _aggregate(votes: list[GuidelineSuggestionVoteRow]) -> dict[str, int]:
    """Fold raw vote rows into the frontend ``SuggestionSignal`` shape."""
    sig = _empty_signal()
    for v in votes:
        if v.verdict in SUGGESTION_VERDICTS:
            sig[v.verdict] += 1
            sig["ratings"] += 1
            if v.verified_vote:
                sig["verified"] += 1
    return sig


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


def synthesis_translation_from_row(
    row: GuidelineSynthesisTranslationRow,
) -> GuidelineSynthesisTranslation:
    return GuidelineSynthesisTranslation(
        disease_slug=row.disease_slug,
        locale=row.locale,
        title=row.title,
        based_on=row.based_on,
        synth_disclaimer=row.synth_disclaimer,
        sections=list(row.sections or []),
        what_to_do_now=row.what_to_do_now,
        red_flags=row.red_flags,
        source_hash=row.source_hash,
        source_version=row.source_version,
        source_model=row.source_model,
        translated_at=row.translated_at,
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
    """Port — the read + suggestion-signal surface :class:`GuidelinesService` uses."""

    def list_source_documents(self, disease_slug: str) -> list[SourceDocument]: ...
    def get_synthesis(self, disease_slug: str) -> GuidelineSynthesis | None: ...
    def list_suggestions(self, disease_slug: str) -> list[GuidelineSuggestion]: ...
    def get_synthesis_signals(
        self, disease_slug: str
    ) -> dict[str, SynthSectionSignal]: ...

    # -- suggestion-rating write loop (SIG-1) -------------------------------
    def suggestion_exists(self, disease_slug: str, suggestion_id: str) -> bool: ...
    def set_suggestion_vote(
        self,
        disease_slug: str,
        suggestion_id: str,
        user_id: str,
        verdict: str,
        verified_vote: bool,
    ) -> dict[str, int]:
        """Upsert one user's vote; return the recomputed aggregate signal."""
        ...

    def clear_suggestion_vote(
        self, disease_slug: str, suggestion_id: str, user_id: str
    ) -> dict[str, int]:
        """Remove one user's vote; return the recomputed aggregate signal."""
        ...

    def user_suggestion_votes(
        self, disease_slug: str, user_id: str
    ) -> dict[str, str]:
        """``{suggestion_id: verdict}`` for one user across a disease."""
        ...


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

    def replace_source_documents(self, disease_slug: str, docs: list[dict]) -> None:
        """Replace the whole source shelf for ``disease_slug`` (delete + bulk insert).

        The shelf-builder workflow re-derives the full shelf each run, so old rows
        for this disease are cleared first; ``sort_order`` follows list order. One
        transaction.
        """
        with Session(self._engine) as session, session.begin():
            session.execute(
                delete(SourceDocumentRow).where(
                    SourceDocumentRow.disease_slug == disease_slug
                )
            )
            for sort_order, doc in enumerate(docs):
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

    # -- suggestion-rating write loop (SIG-1) -------------------------------

    def suggestion_exists(self, disease_slug: str, suggestion_id: str) -> bool:
        with Session(self._engine) as session:
            return (
                session.get(GuidelineSuggestionRow, (disease_slug, suggestion_id))
                is not None
            )

    @staticmethod
    def _recompute_signal(
        session: Session, disease_slug: str, suggestion_id: str
    ) -> dict[str, int]:
        """Re-fold votes into the aggregate and write it onto the suggestion row."""
        votes = list(
            session.scalars(
                select(GuidelineSuggestionVoteRow).where(
                    GuidelineSuggestionVoteRow.disease_slug == disease_slug,
                    GuidelineSuggestionVoteRow.suggestion_id == suggestion_id,
                )
            )
        )
        sig = _aggregate(votes)
        row = session.get(GuidelineSuggestionRow, (disease_slug, suggestion_id))
        if row is not None:
            row.signal = sig  # reassign so the ORM flags the JSON column dirty
        return sig

    def set_suggestion_vote(
        self,
        disease_slug: str,
        suggestion_id: str,
        user_id: str,
        verdict: str,
        verified_vote: bool,
    ) -> dict[str, int]:
        now = _now_iso()
        with Session(self._engine) as session, session.begin():
            row = session.get(
                GuidelineSuggestionVoteRow,
                (disease_slug, suggestion_id, user_id),
            )
            if row is None:
                session.add(
                    GuidelineSuggestionVoteRow(
                        disease_slug=disease_slug,
                        suggestion_id=suggestion_id,
                        user_id=user_id,
                        verdict=verdict,
                        verified_vote=1 if verified_vote else 0,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                row.verdict = verdict
                row.verified_vote = 1 if verified_vote else 0
                row.updated_at = now
            session.flush()
            return self._recompute_signal(session, disease_slug, suggestion_id)

    def clear_suggestion_vote(
        self, disease_slug: str, suggestion_id: str, user_id: str
    ) -> dict[str, int]:
        with Session(self._engine) as session, session.begin():
            session.execute(
                delete(GuidelineSuggestionVoteRow).where(
                    GuidelineSuggestionVoteRow.disease_slug == disease_slug,
                    GuidelineSuggestionVoteRow.suggestion_id == suggestion_id,
                    GuidelineSuggestionVoteRow.user_id == user_id,
                )
            )
            session.flush()
            return self._recompute_signal(session, disease_slug, suggestion_id)

    def user_suggestion_votes(
        self, disease_slug: str, user_id: str
    ) -> dict[str, str]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(GuidelineSuggestionVoteRow).where(
                    GuidelineSuggestionVoteRow.disease_slug == disease_slug,
                    GuidelineSuggestionVoteRow.user_id == user_id,
                )
            )
            return {r.suggestion_id: r.verdict for r in rows}


class InMemoryGuidelinesRepo:
    """Dict-backed fake for service/API tests (and DB-less dev)."""

    def __init__(self) -> None:
        self.source_documents: dict[str, list[SourceDocument]] = {}
        self.synthesis: dict[str, GuidelineSynthesis] = {}
        self.suggestions: dict[str, list[GuidelineSuggestion]] = {}
        self.signals: dict[str, dict[str, SynthSectionSignal]] = {}
        # (disease_slug, suggestion_id, user_id) -> (verdict, verified_vote)
        self.votes: dict[tuple[str, str, str], tuple[str, bool]] = {}

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

    # -- suggestion-rating write loop (SIG-1) -------------------------------

    def suggestion_exists(self, disease_slug: str, suggestion_id: str) -> bool:
        return any(
            s.id == suggestion_id for s in self.suggestions.get(disease_slug, [])
        )

    def _recompute(self, disease_slug: str, suggestion_id: str) -> dict[str, int]:
        sig = _empty_signal()
        for (slug, sid, _uid), (verdict, verified) in self.votes.items():
            if slug == disease_slug and sid == suggestion_id and verdict in SUGGESTION_VERDICTS:
                sig[verdict] += 1
                sig["ratings"] += 1
                if verified:
                    sig["verified"] += 1
        # Mirror the aggregate onto the stored suggestion (frozen → replace).
        from dataclasses import replace

        items = self.suggestions.get(disease_slug, [])
        for i, s in enumerate(items):
            if s.id == suggestion_id:
                items[i] = replace(s, signal=dict(sig))
                break
        return sig

    def set_suggestion_vote(
        self,
        disease_slug: str,
        suggestion_id: str,
        user_id: str,
        verdict: str,
        verified_vote: bool,
    ) -> dict[str, int]:
        self.votes[(disease_slug, suggestion_id, user_id)] = (verdict, verified_vote)
        return self._recompute(disease_slug, suggestion_id)

    def clear_suggestion_vote(
        self, disease_slug: str, suggestion_id: str, user_id: str
    ) -> dict[str, int]:
        self.votes.pop((disease_slug, suggestion_id, user_id), None)
        return self._recompute(disease_slug, suggestion_id)

    def user_suggestion_votes(
        self, disease_slug: str, user_id: str
    ) -> dict[str, str]:
        return {
            sid: verdict
            for (slug, sid, uid), (verdict, _v) in self.votes.items()
            if slug == disease_slug and uid == user_id
        }


# ---------------------------------------------------------------------------
# Synthesis translation (INSTALL-1 content-translation, PR2 write side).
# ---------------------------------------------------------------------------


class GuidelineSynthesisTranslationRepo(Protocol):
    """Port — the translation worker's write/read surface for synthesis translations."""

    def get(
        self, disease_slug: str, locale: str
    ) -> GuidelineSynthesisTranslation | None: ...

    def upsert(self, translation: GuidelineSynthesisTranslation) -> None:
        """Insert-or-update on the PK ``(disease_slug, locale)``."""
        ...


class SqlaGuidelineSynthesisTranslationRepo:
    """Production ORM impl — ``Session`` per operation against the shared engine."""

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()

    def get(
        self, disease_slug: str, locale: str
    ) -> GuidelineSynthesisTranslation | None:
        with Session(self._engine) as session:
            row = session.get(
                GuidelineSynthesisTranslationRow, (disease_slug, locale)
            )
            return synthesis_translation_from_row(row) if row is not None else None

    def upsert(self, translation: GuidelineSynthesisTranslation) -> None:
        t = translation
        with Session(self._engine) as session, session.begin():
            row = session.get(
                GuidelineSynthesisTranslationRow, (t.disease_slug, t.locale)
            )
            if row is None:
                session.add(
                    GuidelineSynthesisTranslationRow(
                        disease_slug=t.disease_slug,
                        locale=t.locale,
                        title=t.title,
                        based_on=t.based_on,
                        synth_disclaimer=t.synth_disclaimer,
                        source_hash=t.source_hash,
                        translated_at=t.translated_at,
                        sections=list(t.sections or []),
                        what_to_do_now=t.what_to_do_now,
                        red_flags=t.red_flags,
                        source_version=t.source_version,
                        source_model=t.source_model,
                    )
                )
            else:
                row.title = t.title
                row.based_on = t.based_on
                row.synth_disclaimer = t.synth_disclaimer
                row.source_hash = t.source_hash
                row.translated_at = t.translated_at
                row.sections = list(t.sections or [])
                row.what_to_do_now = t.what_to_do_now
                row.red_flags = t.red_flags
                row.source_version = t.source_version
                row.source_model = t.source_model


class InMemoryGuidelineSynthesisTranslationRepo:
    """Dict-backed fake for the translation worker's unit tests."""

    def __init__(self) -> None:
        # (disease_slug, locale) -> GuidelineSynthesisTranslation
        self.translations: dict[tuple[str, str], GuidelineSynthesisTranslation] = {}

    def get(
        self, disease_slug: str, locale: str
    ) -> GuidelineSynthesisTranslation | None:
        return self.translations.get((disease_slug, locale))

    def upsert(self, translation: GuidelineSynthesisTranslation) -> None:
        self.translations[(translation.disease_slug, translation.locale)] = translation


__all__ = [
    "GuidelinesRepo",
    "SqlaGuidelinesRepo",
    "InMemoryGuidelinesRepo",
    "GuidelineSynthesisTranslationRepo",
    "SqlaGuidelineSynthesisTranslationRepo",
    "InMemoryGuidelineSynthesisTranslationRepo",
    "source_document_from_row",
    "synthesis_from_row",
    "synthesis_translation_from_row",
    "suggestion_from_row",
    "signal_from_row",
]
