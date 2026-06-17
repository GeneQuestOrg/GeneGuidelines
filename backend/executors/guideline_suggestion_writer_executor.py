"""Executor for the ``guideline_suggestion_writer`` node — the monitor's tail.

Maps the level-b deltas (``GuidelineSuggestionsOutput`` from the delta node) onto
the GL-4 ``guideline_suggestions`` shape and replaces the disease's suggestions via
``repo.replace_suggestions``. Terminal, idempotent.

Deltas default to ``gate="expert"`` — promotion to the parent view is a separate
signal-driven decision (D5), never the engine's call. An empty delta set is valid
(most monitor runs change nothing) and simply clears stale suggestions.
"""
from __future__ import annotations

import logging
import re

from .base import NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)


class GuidelineSuggestionWriterExecutor(NodeExecutor):
    """Persist level-b deltas into guideline_suggestions."""

    def __init__(self, repo=None) -> None:
        self._repo = repo  # injectable for tests

    @classmethod
    def node_type(cls) -> str:
        return "guideline_suggestion_writer"

    def _get_repo(self):
        if self._repo is not None:
            return self._repo
        from ..guidelines.repository import SqlaGuidelinesRepo

        return SqlaGuidelinesRepo()

    async def execute(self, input: NodeInput) -> NodeOutput:
        initial = input.initial_data or input.context.get("initial") or {}
        context = input.context or {}
        slug = str(initial.get("disease_slug") or "").strip().lower()
        if not slug:
            return NodeOutput(data={"ok": False, "error": "disease_slug missing in flow context."})

        # Valid section ids (from the monitor-search node) — drop deltas that target
        # a section that doesn't exist in the synthesis.
        search_out = context.get("gsd-search") if isinstance(context.get("gsd-search"), dict) else {}
        valid_sections = {
            str(s.get("id")): str(s.get("title") or s.get("id"))
            for s in (search_out.get("sections") or [])
            if isinstance(s, dict) and s.get("id")
        }

        deltas = _find_deltas(context)
        suggestions: list[dict] = []
        seen_ids: set[str] = set()
        dropped_offsection = 0
        for d in deltas:
            if not isinstance(d, dict):
                continue
            target = str(d.get("target_section") or "").strip()
            if valid_sections and target not in valid_sections:
                dropped_offsection += 1
                continue
            sug_id = _slug_id(d, seen_ids)
            seen_ids.add(sug_id)
            suggestions.append(
                {
                    "id": sug_id,
                    "kind": str(d.get("kind") or "addition").strip().lower(),
                    "targetSection": target,
                    "sectionLabel": str(d.get("section_label") or "").strip()
                    or valid_sections.get(target, target),
                    "title": str(d.get("title") or "").strip(),
                    "summary": str(d.get("summary") or "").strip(),
                    "rationale": str(d.get("rationale") or "").strip(),
                    "evidence": str(d.get("evidence") or "moderate").strip().lower(),
                    "gate": "expert",  # promotion to parent = D5 signal, never the engine
                    "citations": [str(c).strip() for c in (d.get("citations") or []) if str(c).strip().isdigit()],
                    "signal": {},
                    "comments": [],
                }
            )

        try:
            self._get_repo().replace_suggestions(slug, suggestions)
        except Exception as exc:  # noqa: BLE001 — a write failure must fail the node
            log.warning("guideline_suggestion_writer: replace failed for %s: %s", slug, exc)
            return NodeOutput(data={"ok": False, "error": f"suggestion write failed: {exc}"})

        return NodeOutput(
            data={
                "ok": True,
                "slug": slug,
                "suggestionCount": len(suggestions),
                "droppedOffSection": dropped_offsection,
            }
        )


def _find_deltas(context: dict) -> list:
    primary = context.get("gsd-delta")
    if isinstance(primary, dict) and isinstance(primary.get("suggestions"), list):
        return primary["suggestions"]
    for out in context.values():
        if isinstance(out, dict) and isinstance(out.get("suggestions"), list):
            return out["suggestions"]
    return []


def _slug_id(delta: dict, seen: set[str]) -> str:
    """Stable suggestion id: 'sg-<source_pmid>' or a slug of the title."""
    base = str(delta.get("source_pmid") or "").strip()
    if base.isdigit():
        sug_id = f"sg-{base}"
    else:
        slug = re.sub(r"[^a-z0-9]+", "-", str(delta.get("title") or "sg").lower()).strip("-")[:32]
        sug_id = f"sg-{slug or 'item'}"
    n, out = 1, sug_id
    while out in seen:
        n += 1
        out = f"{sug_id}-{n}"
    return out
