"""A side-by-side on production data without touching it: build a disease's block with a chosen pipeline, read the live block, and write both to local files for a person to compare. Nothing is written to the database (the spend goes to a local cap, not the research ledger). It calls Claude, so it costs money; the CLI asks for ``--yes``."""

from __future__ import annotations

import asyncio
import functools
import json
import os
from pathlib import Path
from typing import Any

from .block import build_published_block
from .deps import PIPELINES, production_reader
from .llm import (
    GENERATOR_NODE_TOKENS,
    GENERATOR_SPEC,
    RUN_CAP_USD,
    VERIFIER_NODE_TOKENS,
    VERIFIER_SPEC,
    BudgetExceeded,
    ClaudePointsCaller,
    call_cost,
    worst_case_cost,
)
from .models import BlockOutcome
from .prompts import worked_example
from .repository import SqlaGuidelinePointsRepo
from .service import HAND_WRITTEN
from .sources import select_documents


class LocalBudget:
    """The run's cost cap, kept in memory: a dry run writes nothing to the database, not even the token ledger."""

    def __init__(self, cap_usd: float) -> None:
        self.cap_usd, self.spent = cap_usd, 0.0

    def reserve(self, model: str, prompt_chars: int, max_tokens: int) -> float:
        worst = worst_case_cost(model, prompt_chars, max_tokens)
        if self.spent + worst > self.cap_usd:
            raise BudgetExceeded(f"this call could cost {worst:.2f} USD; the dry run has spent {self.spent:.2f} of its {self.cap_usd:.2f} USD cap")
        return worst

    def settle(self, ticket: Any, model: str, usage: dict[str, Any], role: str, error: str | None) -> float | None:
        cost = call_cost(model, usage)
        self.spent += cost or 0.0
        return cost


async def dry_run(slugs: list[str], out: Path, *, pipeline: str) -> list[dict[str, Any]]:
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    out.mkdir(parents=True, exist_ok=True)
    reader, repo, build = production_reader(), SqlaGuidelinePointsRepo(), PIPELINES[pipeline]
    summary = []
    for slug in slugs:
        if slug in HAND_WRITTEN:
            continue
        budget = LocalBudget(RUN_CAP_USD)
        writer = ClaudePointsCaller(GENERATOR_SPEC, api_key=key, node_max_tokens=GENERATOR_NODE_TOKENS, budget=budget)
        checker = ClaudePointsCaller(VERIFIER_SPEC, api_key=key, node_max_tokens=VERIFIER_NODE_TOKENS, budget=budget)
        identity = await asyncio.to_thread(reader.identity_for, slug)
        if identity is None:
            continue
        shelf = await asyncio.to_thread(reader.list_shelf, slug)
        index = await asyncio.to_thread(reader.load_index)
        docs = await asyncio.to_thread(reader.load_documents, shelf, index)
        selected, notes = await asyncio.to_thread(functools.partial(select_documents, docs, identity=identity, genereviews=index))
        record = await build(disease_name=identity.name, docs=selected, writer=writer, checker=checker, example=worked_example())
        new_block = build_published_block({"publish": record.outcome is BlockOutcome.PUBLISHED, "accepted": list(record.accepted)}, selected)
        live = await asyncio.to_thread(repo.get, slug)
        entry = {"slug": slug, "pipeline": record.pipeline, "outcome": record.outcome.value, "clean": record.clean, "cost_usd": round(budget.spent, 4), "selection_notes": notes, "new_block": new_block, "live_block": live.published_block if live else None, "record": record.raw}
        (out / f"{slug}.json").write_text(json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8")
        summary.append(entry)
    (out / "side-by-side.md").write_text(_markdown(summary), encoding="utf-8")
    return summary


def _points(block: dict[str, Any] | None) -> list[str]:
    if not block:
        return ["_(no block)_"]
    lines = [f"**{block.get('title_pl')}**", ""]
    for p in block.get("points") or []:
        lines += [f"- {p['summary_pl']}", f"  - Pytanie: {p['question_pl']}", f"  - Cytat ({p.get('doc_citation', p['doc_id'])}): _{p['quote']}_"]
    return lines


def _markdown(entries: list[dict[str, Any]]) -> str:
    lines = ["# Guideline points: live block and new block, side by side", ""]
    for e in entries:
        lines += [f"## {e['slug']} — new: {e['pipeline']}, {e['outcome']}, clean={e['clean']}, {e['cost_usd']:.2f} USD", "", "### Live now", "", *_points(e["live_block"]), "", "### New", "", *_points(e["new_block"]), ""]
    return "\n".join(lines)


__all__ = ["LocalBudget", "dry_run"]
