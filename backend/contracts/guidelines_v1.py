"""Guideline synthesis (level a) data contract — v1.

Single source of truth for the synthesis-over-the-shelf contract: the schema
version, the canonical section spec, and the shape limits. Mirrors the existing
versioned-contract convention (``agent_api_v1`` / ``parent_pathway_v1``).

Three layers must agree for this contract (see
``docs/produkty/geneguidelines/realizacja/kontrakty-danych.md``):

    FE type ``guidelineSynthesis.ts``  ↔  ``SynthesisResponse`` (guidelines/contracts.py)
                                       ↔  ``GuidelineSynthesisRow`` (guidelines/orm.py)

The AI side is enforced by the ``GuidelineSectionOutput`` preset
(``agents/schemas.py`` → ``PRESET_OUTPUT_SCHEMAS["guideline_section"]``); the
``guideline_synthesis_writer`` executor maps preset → contract.

Versioning policy: a breaking change (removed/renamed field, changed
type/semantics) ships as ``guidelines_v2.py`` with ``"v2"``; additive optional
fields keep ``"v1"`` (FE camelCase types are frozen — add only optional fields).
Persisted rows are implicitly ``v1``; a ``schema_version`` column is added only
at the first concurrent-version need (not speculatively).
"""
from __future__ import annotations

from typing import TypedDict

GUIDELINE_SYNTHESIS_CONTRACT_VERSION = "v1"

# Epistemic taxonomy (wizja 04): a = synthesis over existing guideline,
# b = delta suggestions, c = no guideline (baseline).
EPISTEMIC_LEVELS: tuple[str, ...] = ("a", "b", "c")
EPISTEMIC_LEVEL_SYNTHESIS = "a"

# Shape limits — kept in sync with the GuidelineSectionOutput preset and the
# section prompts in flows/specs/guideline_synthesis.json.
MIN_PARAGRAPHS_PER_SECTION = 1
MAX_PARAGRAPHS_PER_SECTION = 6


class SectionSpec(TypedDict):
    """One synthesis section: stable id + human title.

    ``id`` MUST match the ``gs-sec-<id>`` node id in
    ``flows/specs/guideline_synthesis.json`` and is what the writer uses for a
    stable section id/title independent of LLM drift.
    """

    id: str
    title: str


# Canonical section spec for the level-(a) synthesis flow. Imported by the
# trigger (routers/pipeline.py) and mirrored by the flow spec's gs-sec-* nodes.
SYNTHESIS_SECTIONS: list[SectionSpec] = [
    {"id": "diagnosis", "title": "1. Diagnosis"},
    {"id": "histopathology", "title": "2. Histopathology and genetics"},
    {"id": "therapy", "title": "3. Therapy"},
    {"id": "surgery", "title": "4. Indications for surgery"},
    {"id": "monitoring", "title": "5. Monitoring and follow-up"},
]

__all__ = [
    "GUIDELINE_SYNTHESIS_CONTRACT_VERSION",
    "EPISTEMIC_LEVELS",
    "EPISTEMIC_LEVEL_SYNTHESIS",
    "MIN_PARAGRAPHS_PER_SECTION",
    "MAX_PARAGRAPHS_PER_SECTION",
    "SectionSpec",
    "SYNTHESIS_SECTIONS",
]
