"""Map a successful PubMed agent run output into a publishable guideline document.

The PubMed pipeline emits an HTML-blob payload (``guideline_html`` plus per-topic
``*_html`` strings, an ``article_count``, ``evidence_score``, etc.). The public
guideline reader expects the canonical structured shape declared by
:class:`backend.content_models.GuidelineDocumentResponse` — sections with stable
ids and paragraph-level citations.

This module bridges the two for the **AI-draft path** (no human review yet):
each non-empty topic ``*_html`` becomes one section with a single paragraph
holding the raw HTML and the PMIDs extracted from it. Fine-grained
paragraph-level chunking is a P0.2' concern (PR review polish over ai-draft) and
deliberately out of scope here.

The function is pure: no DB, no logging side-effects. It validates its output
against :class:`GuidelineDocumentResponse` (which is ``extra="forbid"``) before
returning, so callers can trust the dict round-trips through the API.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from ..content_models import GuidelineDocumentResponse


class GuidelinePublishError(ValueError):
    """Raised when the agent output cannot be mapped to a renderable document."""


# Order matters: this is the order sections appear in the public reader.
_SECTION_MAPPING: tuple[tuple[str, str, str], ...] = (
    # (input_html_key, section_id, section_title)
    ("diagnostic_algorithm_html", "diagnostics", "Diagnostics"),
    ("red_flags_html", "red-flags", "Red Flags & Contraindications"),
    ("treatment_steps_html", "treatment", "Treatment & Management"),
    ("monitoring_protocol_html", "monitoring", "Monitoring Protocol"),
    ("follow_up_schedule_html", "follow-up", "Follow-Up & Prognosis"),
    ("evidence_gaps_html", "evidence-gaps", "Evidence Gaps & References"),
)

# Reused from flows/pubmed/code_nodes.py — keep in sync.
_PMID_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bPMID[:\s]+(\d{6,10})\b", re.IGNORECASE),
    re.compile(r"/pubmed/(\d{6,10})"),
    re.compile(r"pubmed\.ncbi[^/\"'\s]*/(\d{6,10})"),
)

_MAX_CITATIONS_PER_PARAGRAPH = 30


def _extract_pmids(html: str) -> list[str]:
    """Pull PMIDs out of an HTML blob. Deduped, sorted ascending, capped."""
    if not html:
        return []
    found: set[str] = set()
    for pattern in _PMID_PATTERNS:
        for match in pattern.findall(html):
            found.add(str(match))
    return sorted(found, key=int)[:_MAX_CITATIONS_PER_PARAGRAPH]


def _build_sections(output_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn each non-empty *_html topic into one section with one paragraph."""
    sections: list[dict[str, Any]] = []
    for html_key, section_id, section_title in _SECTION_MAPPING:
        html = str(output_json.get(html_key) or "").strip()
        if not html:
            continue
        sections.append(
            {
                "id": section_id,
                "title": section_title,
                "intro": None,
                "paragraphs": [
                    {
                        "id": f"ai-{section_id}-1",
                        "text": html,
                        "citations": _extract_pmids(html),
                    }
                ],
            }
        )
    return sections


def _based_on_summary(output_json: dict[str, Any]) -> str:
    """One-line provenance: article count + evidence score, defensive on types."""
    try:
        article_count = int(output_json.get("article_count") or 0)
    except (TypeError, ValueError):
        article_count = 0
    try:
        evidence_score = int(output_json.get("evidence_score") or 0)
    except (TypeError, ValueError):
        evidence_score = 0
    return (
        f"PubMed sweep · {article_count} articles · "
        f"evidence score {evidence_score} (AI draft, pending review)"
    )


def build_ai_draft_document_payload(
    *,
    disease_slug: str,
    disease_name: str,
    output_json: dict[str, Any],
    execution_id: str,
) -> dict[str, Any]:
    """Map a PubMed agent run output to a GuidelineDocumentResponse-shaped dict.

    Raises :class:`GuidelinePublishError` when the input has no renderable
    sections (every topic ``*_html`` empty) — the upstream caller should log
    a warning and skip the publish step rather than write a useless empty doc.

    The return value has already been validated against
    :class:`GuidelineDocumentResponse`; callers can persist it as-is.
    """
    if not isinstance(output_json, dict):
        raise GuidelinePublishError("output_json must be a dict")

    slug = (disease_slug or "").strip().lower()
    if not slug:
        raise GuidelinePublishError("disease_slug is required")

    name = (disease_name or "").strip()
    if not name:
        # Fall back to whatever the agent saw, then to the slug.
        name = str(output_json.get("disease_name") or "").strip() or slug

    sections = _build_sections(output_json)
    if not sections:
        raise GuidelinePublishError(
            "no renderable sections in pubmed output (all *_html empty)"
        )

    exec_id = (execution_id or "").strip()
    version_tag = f"ai-draft-{exec_id[:8]}" if exec_id else "ai-draft"

    payload: dict[str, Any] = {
        "slug": slug,
        "title": f"{name} — clinical guideline (AI draft)",
        "version": version_tag,
        "lastUpdated": datetime.now(UTC).date().isoformat(),
        "basedOn": _based_on_summary(output_json),
        "status": "ai-draft",
        "statusBy": None,
        "sections": sections,
    }

    # Validate at the boundary so we fail loudly here rather than at API read.
    GuidelineDocumentResponse.model_validate(payload)
    return payload


__all__ = [
    "GuidelinePublishError",
    "build_ai_draft_document_payload",
]
