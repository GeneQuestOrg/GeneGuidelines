"""Building, checking and storing one disease's "What the guideline says about diagnosis – to show your doctor" block: the one place that runs a pipeline and decides what is stored.

Three ways in, all through :class:`PointsService` (production wiring in ``deps.default_points_service``):

- **After a synthesis.** The synthesis completion hook (``routers/agent.py``) runs it for the disease; nothing happens when the stored block was built from the same shelf (``models.shelf_hash``), so re-synthesising does not re-buy the block.
- **Backfill.** ``POST /api/pipeline/guideline-points/backfill`` (superadmin, ``api.py``) or ``python -m backend.guidelines.points.cli [slug …]``, one disease after another.
- **One disease.** The same CLI with one slug, ``--force`` to rebuild an unchanged shelf.

FD is never generated: its page keeps the hand-written block, which is also the worked example for every other disease (``fd_worked_example.json``).

What is stored: a run that publishes replaces the block and records the shelf it was built from, so the same shelf is not paid for twice. A run in which a model call failed and that does not publish stores nothing over an existing block, which stays live. A run that does not publish otherwise withdraws the block and records no shelf, so the next synthesis or backfill tries again.

Every dependency comes in through the constructor (repository, shelf reader, model callers, budget guard, run lock), so tests pass fakes instead of patching module paths.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...shared.monitoring import report_limit
from ..relevance import DiseaseIdentity
from .block import build_published_block
from .loop import build_points_block
from .models import BlockOutcome, BlockRecord, SourceDoc, shelf_hash
from .ports import PointsCaller
from .prompts import worked_example
from .repository import GuidelinePointsRepo, StoredPoints, stamped
from .run_lock import RunLock
from .sources import select_documents

log = logging.getLogger(__name__)

HAND_WRITTEN = frozenset({"fd"})

# The limits a run can hit, as the loop records them on a dropped point: (start of the reason, limit name, message).
_DROP_LIMITS = (
    ("over the limit of", "max_points", "points dropped over the point limit"),
    ("still failing after the last revision round", "revision_rounds", "points dropped after the last revision round"),
)

Callers = tuple[PointsCaller, PointsCaller, str]


@dataclass(frozen=True)
class ShelfReader:
    """What a run reads before any model call: the disease's stored shelf, its identity, the GeneReviews index and the documents' full text."""

    list_shelf: Callable[[str], list[Any]]
    identity_for: Callable[[str], DiseaseIdentity | None]
    load_index: Callable[[], dict[str, Any]]
    load_documents: Callable[[list[Any], dict[str, Any]], list[SourceDoc]]


class PointsService:
    def __init__(
        self,
        *,
        repo: GuidelinePointsRepo,
        reader: ShelfReader,
        make_callers: Callable[[str, str], Callers],
        budget_block_reason: Callable[[], str | None],
        lock: RunLock,
        list_slugs: Callable[[], list[str]] = list,
        example: Callable[[], dict[str, Any] | None] = worked_example,
    ) -> None:
        self.repo = repo
        self.reader = reader
        self.make_callers = make_callers
        self.budget_block_reason = budget_block_reason
        self.lock = lock
        self.list_slugs = list_slugs
        self.example = example

    async def run(self, slug: str, *, force: bool = False) -> dict[str, Any]:
        """Build, check and store one disease's block. Returns what happened; never raises for a failed model call."""
        slug = (slug or "").strip().lower()
        if slug in HAND_WRITTEN:
            return {"slug": slug, "status": "skipped", "reason": "this disease keeps its hand-written block"}
        with self.lock.hold(slug) as held:
            if not held:
                return {"slug": slug, "status": "skipped", "reason": "a run for this disease is already in progress"}
            return await self._run(slug, force=force)

    async def backfill(self, slugs: list[str] | None = None, *, force: bool = False) -> list[dict[str, Any]]:
        """Run the given diseases, or every listed catalog disease, one after another; one failure does not stop the rest."""
        if not slugs:
            slugs = await asyncio.to_thread(self.list_slugs)
        results = []
        for slug in slugs:
            try:
                results.append(await self.run(slug, force=force))
            except Exception as exc:  # noqa: BLE001 — one disease must not stop the backfill
                log.exception("guideline points: %s failed", slug)
                results.append({"slug": slug, "status": "error", "reason": f"{type(exc).__name__}: {exc}"})
        return results

    async def _run(self, slug: str, *, force: bool) -> dict[str, Any]:
        shelf = await asyncio.to_thread(self.reader.list_shelf, slug)
        fingerprint = shelf_hash(shelf)
        existing = await asyncio.to_thread(self.repo.get, slug)
        if existing is not None and existing.publish and existing.shelf_hash == fingerprint and not force:
            return {"slug": slug, "status": "unchanged", "publish": True}
        blocked = await asyncio.to_thread(self.budget_block_reason)
        if blocked:
            report_limit("monthly_research_budget", "the guideline-points run did not start", component="guideline_points", disease=slug, reason=blocked)
            return {"slug": slug, "status": "skipped", "reason": f"the monthly research budget is used up ({blocked})"}
        identity = await asyncio.to_thread(self.reader.identity_for, slug)
        if identity is None:
            return {"slug": slug, "status": "skipped", "reason": "not a catalog disease"}
        index = await asyncio.to_thread(self.reader.load_index)
        docs = await asyncio.to_thread(self.reader.load_documents, shelf, index)
        # Relevance matching runs regexes over up to ~700k characters: off the event loop, so public requests do not stall.
        selected, notes = await asyncio.to_thread(lambda: select_documents(docs, identity=identity, genereviews=index))
        generator, verifier, models = self.make_callers(slug, f"gpt-{uuid.uuid4().hex[:12]}")
        raw = await build_points_block(disease_name=identity.name, docs=selected, generator=generator, verifier=verifier, example=self.example())
        raw["selection_notes"] = notes
        raw["documents_considered"] = [{"doc_id": d.doc_id, "grade": d.grade, "text_status": d.text_status, "licence": d.license} for d in docs]
        record = BlockRecord.from_loop(raw)
        _report_limits(slug, record)
        return await self._store(slug, record, build_published_block(raw, selected), fingerprint, existing, models)

    async def _store(self, slug: str, record: BlockRecord, block: dict[str, Any] | None, fingerprint: str, existing: StoredPoints | None, models: str) -> dict[str, Any]:
        cost = round(record.cost_usd, 4)
        if not block and record.failed_calls and existing is not None and existing.publish:
            # A passing outage must not take a published block off the page.
            log.warning("guideline points: %s had %d failed model call(s); the previous block stays", slug, record.failed_calls)
            return {"slug": slug, "status": "failed", "reason": record.reason or "a model call failed", "cost_usd": cost}
        # Only a published block records its shelf; anything else is retried by the next synthesis or backfill.
        stored = StoredPoints(slug=slug, publish=bool(block), reason=record.reason, shelf_hash=fingerprint if block else "", block=block, record=record.stored_record, models=models)
        await asyncio.to_thread(self.repo.save, stamped(stored, record.cost_usd))
        log.info("guideline points: %s stored (publish=%s, %d points, %.2f USD)", slug, bool(block), len(record.accepted), record.cost_usd)
        return {"slug": slug, "status": "stored", "publish": bool(block), "points": len(record.accepted), "reason": record.reason, "cost_usd": cost}


def _report_limits(slug: str, record: BlockRecord) -> None:
    """One limit report per kind of limit this run hit: documents left out for the input budget, points dropped at a limit. Answers cut off or refused are reported by the Claude adapter itself."""
    over_budget = [note for note in record.raw.get("selection_notes") or [] if "input budget" in note]
    if over_budget:
        report_limit("input_budget", "documents left out of the guideline-points input", component="guideline_points", disease=slug, documents=len(over_budget))
    dropped = [str(d.get("why") or "") for d in record.raw.get("dropped") or []]
    for marker, limit, message in _DROP_LIMITS:
        count = sum(1 for why in dropped if why.startswith(marker))
        if count:
            report_limit(limit, message, component="guideline_points", disease=slug, points=count)
    if record.outcome is BlockOutcome.BUDGET_EXCEEDED:
        report_limit("run_cost_cap", "a guideline-points run stopped at its cost cap", component="guideline_points", disease=slug)


__all__ = ["HAND_WRITTEN", "PointsService", "ShelfReader"]
