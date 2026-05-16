"""Typed string identifiers — zero-runtime-cost type discipline.

Why this file exists:

Most of the backend passes free-form ``str`` for things that are conceptually
different (a disease slug, a PubMed identifier, a workflow run id, a node id
inside a flow). The compiler cannot catch when these get swapped, so a typo
goes silently through. ``NewType`` gives each identifier its own type at
type-check time without any runtime overhead — ``DiseaseSlug("fd")`` is
literally ``"fd"`` at runtime, but mypy/pyright reject passing a ``RunId``
where a ``DiseaseSlug`` is expected.

Usage is opt-in. New code should reach for these types; existing code is
migrated as it gets touched in Phase 2.

Example::

    from backend.shared.value_objects import DiseaseSlug, RunId

    def fetch_disease(slug: DiseaseSlug) -> Disease | None: ...
    def fetch_run(run_id: RunId) -> Run | None: ...

    fetch_disease(DiseaseSlug("fd"))   # ok
    fetch_run(RunId(42))               # ok
    fetch_disease(RunId(42))           # type error at static analysis time
"""

from __future__ import annotations

from typing import NewType

# Disease catalogue identifiers (e.g. "fd", "mas", "noonan"). Always lowercase,
# ascii, hyphenated. The DB column is ``diseases.slug``.
DiseaseSlug = NewType("DiseaseSlug", str)

# PubMed identifier. Always a numeric string in PubMed convention (so kept as
# str to preserve leading-zero or formatting surprises).
PmidStr = NewType("PmidStr", str)

# DOI string (e.g. "10.1234/abc.5678"). Lowercased on entry; stored as TEXT.
DoiStr = NewType("DoiStr", str)

# Workflow run / case identifiers. Backed by the ``tickets`` table for now —
# ADR 002 plans a rename to ``runs`` in Phase 1 of the data-model migration.
RunId = NewType("RunId", int)

# Per-execution identifier returned by ``POST /api/agent/run/{ticket_id}`` and
# used as the SSE channel key.
ExecutionId = NewType("ExecutionId", str)

# Node identifier inside a flow definition (e.g. "pm-1", "df-20", "start"). The
# DB column is ``flow_definitions.node_id``; unique per flow_key.
NodeId = NewType("NodeId", str)

# Flow definition key (e.g. "pubmed", "doctor_finder", "parent_pathway"). DB
# column ``flow_definitions.flow_key``; primary scoping key for nodes.
FlowKey = NewType("FlowKey", str)

# MCP tool name in the canonical snake_case form (e.g. "pubmed_search_articles").
ToolName = NewType("ToolName", str)


__all__ = [
    "DiseaseSlug",
    "PmidStr",
    "DoiStr",
    "RunId",
    "ExecutionId",
    "NodeId",
    "FlowKey",
    "ToolName",
]
