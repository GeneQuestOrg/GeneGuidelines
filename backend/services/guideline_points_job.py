"""Build and store a disease's "What the guideline says about diagnosis – to show your doctor" block.

Three ways in:

- **After a synthesis.** The synthesis completion hook (``routers/agent.py``) calls :func:`run_guideline_points` for the disease; it does nothing when the stored block was built from the same shelf (``store.shelf_hash``), so re-synthesising does not re-buy the block.
- **Backfill.** ``POST /api/pipeline/guideline-points/backfill`` (superadmin) or ``python -m backend.services.guideline_points_job [slug …]`` runs it for every listed catalog disease, one after another.
- **One disease.** The same CLI with one slug, ``--force`` to rebuild an unchanged shelf.

FD is never generated: its page keeps the hand-written block, which is also the worked example for every other disease (``points/fd_worked_example.json``).

The loop runs on Claude through the production adapter (ADR 006): generator Sonnet 5.5, verifier and coverage reviewer Opus 5.5. Each call's tokens go into the research token ledger, and a run does not start while the monthly research budget is used up.

What is stored: a run that publishes replaces the block and records the shelf it was built from, so the same shelf is not paid for twice. A run in which any model call failed stores nothing over an existing block, which stays live. A clean run that does not publish withdraws the block and records no shelf, so the next synthesis or backfill tries again; that is what keeps a disease from getting stuck on a passing outage or a GeneReviews chapter the worker has not stored yet.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from typing import Any

from ..shared.monitoring import report_limit

log = logging.getLogger(__name__)

HAND_WRITTEN = frozenset({"fd"})

# One run per disease at a time within a process: a double-clicked backfill and the after-synthesis hook must not pay for the same disease twice. Across processes the store's upsert keeps the last write.
_RUNNING: set[str] = set()


class _LedgerBudget:
    """Records each Claude call in the research token ledger (``token_usage``). It does not refuse single calls; :func:`run_guideline_points` checks the monthly guard once, before a run starts."""

    def __init__(self, slug: str, execution_id: str) -> None:
        self.slug, self.execution_id = slug, execution_id

    def reserve(self, model: str, prompt_chars: int, max_tokens: int) -> None:
        return None

    def settle(self, ticket: Any, model: str, usage: dict, role: str, error: str | None) -> float | None:
        try:
            from ..research_queue.token_budget import record_usage

            prompt = sum(int(usage.get(k, 0) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
            completion = int(usage.get("output_tokens", 0) or 0)
            record_usage(execution_id=self.execution_id, model_spec=f"anthropic:{model}", prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion, disease_slug=self.slug)
        except Exception:  # noqa: BLE001 — token capture must never break a run
            log.debug("guideline_points_job: token usage not recorded", exc_info=True)
        return _cost(model, usage)


_PRICES = {"claude-opus-5-5": (4.0, 20.0, 0.20, 5.0), "claude-sonnet-5-5": (2.0, 10.0, 0.10, 2.5)}


def _cost(model: str, usage: dict) -> float | None:
    price = _PRICES.get(model)
    if price is None:
        return None
    pin, pout, pread, pwrite = price
    return (int(usage.get("input_tokens", 0) or 0) * pin + int(usage.get("cache_creation_input_tokens", 0) or 0) * pwrite + int(usage.get("cache_read_input_tokens", 0) or 0) * pread + int(usage.get("output_tokens", 0) or 0) * pout) / 1_000_000


def _callers(slug: str, execution_id: str):
    from ..guidelines.points.claude import (
        GENERATOR_NODE_TOKENS,
        GENERATOR_SPEC,
        VERIFIER_NODE_TOKENS,
        VERIFIER_SPEC,
        ClaudePointsCaller,
    )

    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; the guideline-points loop runs on Claude only (ADR 006)")
    budget = _LedgerBudget(slug, execution_id)
    generator = ClaudePointsCaller(GENERATOR_SPEC, api_key=key, node_max_tokens=GENERATOR_NODE_TOKENS, budget=budget)
    verifier = ClaudePointsCaller(VERIFIER_SPEC, api_key=key, node_max_tokens=VERIFIER_NODE_TOKENS, budget=budget)
    return generator, verifier, f"generator {GENERATOR_SPEC}; verifier and coverage {VERIFIER_SPEC}"


_DROP_LIMITS = (
    ("over the limit of", "max_points", "points dropped over the point limit"),
    ("still failing after the last revision round", "revision_rounds", "points dropped after the last revision round"),
)


def _report_limits(slug: str, record: dict[str, Any]) -> None:
    """One limit report per kind of limit this run hit: documents left out for the input budget, points dropped at a limit. Answers cut off or refused are reported by the Claude adapter itself."""
    over_budget = [note for note in record.get("selection_notes") or [] if "input budget" in note]
    if over_budget:
        report_limit("input_budget", "documents left out of the guideline-points input", component="guideline_points", disease=slug, documents=len(over_budget))
    dropped = [str(d.get("why") or "") for d in record.get("dropped") or []]
    for marker, limit, message in _DROP_LIMITS:
        count = sum(1 for why in dropped if why.startswith(marker))
        if count:
            report_limit(limit, message, component="guideline_points", disease=slug, points=count)


async def run_guideline_points(slug: str, *, force: bool = False, callers=None, engine=None) -> dict:
    """Build, check and store one disease's block. Returns what happened; never raises for a failed model call."""
    slug = (slug or "").strip().lower()
    if slug in HAND_WRITTEN:
        return {"slug": slug, "status": "skipped", "reason": "this disease keeps its hand-written block"}
    if slug in _RUNNING:
        return {"slug": slug, "status": "skipped", "reason": "a run for this disease is already in progress"}
    _RUNNING.add(slug)
    try:
        return await _run(slug, force=force, callers=callers, engine=engine)
    finally:
        _RUNNING.discard(slug)


async def _run(slug: str, *, force: bool, callers, engine) -> dict:
    import uuid

    from ..guidelines.points.block import published_block
    from ..guidelines.points.loop import build_points_block
    from ..guidelines.points.prompts import worked_example
    from ..guidelines.points.sources import load_shelf_documents, select_documents
    from ..guidelines.points.store import get_points, save_points, shelf_hash
    from ..guidelines.relevance import identity_for_slug
    from ..guidelines.repository import SqlaGuidelinesRepo
    from ..research_queue.token_budget import budget_block_reason
    from ..tools.genereviews_index import load_index

    loop = asyncio.get_running_loop()
    repo = SqlaGuidelinesRepo(engine=engine) if engine is not None else SqlaGuidelinesRepo()
    shelf = await loop.run_in_executor(None, lambda: repo.list_source_documents(slug))
    fingerprint = shelf_hash(shelf)
    existing = await loop.run_in_executor(None, lambda: get_points(slug, engine))
    if existing is not None and existing.publish and existing.shelf_hash == fingerprint and not force:
        return {"slug": slug, "status": "unchanged", "publish": True}
    blocked = await loop.run_in_executor(None, budget_block_reason)
    if blocked:
        report_limit("monthly_research_budget", "the guideline-points run did not start", component="guideline_points", disease=slug, reason=blocked)
        return {"slug": slug, "status": "skipped", "reason": f"the monthly research budget is used up ({blocked})"}
    identity = await loop.run_in_executor(None, lambda: identity_for_slug(slug))
    if identity is None:
        return {"slug": slug, "status": "skipped", "reason": "not a catalog disease"}
    api_key = (os.environ.get("NCBI_API_KEY") or "").strip() or None
    index = await loop.run_in_executor(None, load_index)
    docs = await loop.run_in_executor(None, lambda: load_shelf_documents(shelf, api_key=api_key, genereviews=index))
    # Relevance matching runs regexes over up to ~700k characters: off the event loop, so public requests do not stall.
    selected, notes = await loop.run_in_executor(None, lambda: select_documents(docs, identity=identity, genereviews=index))
    execution_id = f"gpt-{uuid.uuid4().hex[:12]}"
    if callers is None:
        generator, verifier, models = _callers(slug, execution_id)
    else:
        generator, verifier, models = callers
    record = await build_points_block(disease_name=identity.name, docs=selected, generator=generator, verifier=verifier, example=worked_example())
    record["selection_notes"] = notes
    record["documents_considered"] = [{"doc_id": d.doc_id, "grade": d.grade, "text_status": d.text_status, "licence": d.license} for d in docs]
    _report_limits(slug, record)
    block = published_block(record, selected)
    cost = sum(float(c.get("cost_usd_total") or 0.0) for c in record.get("calls") or [])
    failed_calls = [c for c in record.get("calls") or [] if c.get("error")]
    if not block and failed_calls and existing is not None and existing.publish:
        # A passing outage must not take a published block off the page.
        log.warning("guideline_points_job: %s had %d failed model call(s); the previous block stays", slug, len(failed_calls))
        return {"slug": slug, "status": "failed", "reason": record["reason"] or "a model call failed", "cost_usd": round(cost, 4)}
    # Only a published block records its shelf; anything else is retried by the next synthesis or backfill.
    stored_hash = fingerprint if block else ""
    await loop.run_in_executor(None, lambda: save_points(slug=slug, publish=bool(block), reason=record["reason"], shelf_hash=stored_hash, block=block, record=record, models=models, cost_usd=cost, engine=engine))
    log.info("guideline_points_job: %s stored (publish=%s, %d points, %.2f USD)", slug, bool(block), len(record["accepted"]), cost)
    return {"slug": slug, "status": "stored", "publish": bool(block), "points": len(record["accepted"]), "reason": record["reason"], "cost_usd": round(cost, 4)}


async def backfill(slugs: list[str] | None = None, *, force: bool = False) -> list[dict]:
    """Run the job for the given slugs, or every listed catalog disease, one after another."""
    from ..content_db import list_diseases_catalog

    if not slugs:
        slugs = [str(d.get("slug")) for d in await asyncio.to_thread(list_diseases_catalog)]
    results = []
    for slug in slugs:
        try:
            results.append(await run_guideline_points(slug, force=force))
        except Exception as exc:  # noqa: BLE001 — one disease must not stop the backfill
            log.exception("guideline_points_job: %s failed", slug)
            results.append({"slug": slug, "status": "error", "reason": f"{type(exc).__name__}: {exc}"})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and store the guideline-points block for catalog diseases.")
    parser.add_argument("slugs", nargs="*", help="disease slugs (default: every listed catalog disease)")
    parser.add_argument("--force", action="store_true", help="rebuild even when the shelf has not changed")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for result in asyncio.run(backfill(args.slugs or None, force=args.force)):
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
