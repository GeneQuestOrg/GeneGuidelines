"""Guards for parent_pathway agentic synthesis (pp-synth must persist a draft)."""
from __future__ import annotations

from typing import Any


def parent_pathway_synth_missing_draft_error(
    flow_key: str,
    node_id: str,
    store: dict[str, Any],
) -> str | None:
    """Return an error message when pp-synth finished without a saved pathway draft."""
    if (flow_key or "").strip() != "parent_pathway" or (node_id or "").strip() != "pp-synth":
        return None

    initial = store.get("disease_initial")
    if not isinstance(initial, dict):
        initial = store.get("initial") if isinstance(store.get("initial"), dict) else {}
    slug = str((initial or {}).get("disease_slug") or "").strip().lower()
    if not slug:
        return "parent_pathway: disease_slug missing — cannot verify patient chart save."

    try:
        from ...content_db import get_parent_pathway_draft
    except ImportError:
        from content_db import get_parent_pathway_draft  # type: ignore[no-redef]

    if get_parent_pathway_draft(slug) is not None:
        return None

    return (
        "Patient chart was not saved. pp-synth must call submit_parent_pathway with JSON that passes "
        "validate_parent_pathway_json (tool returns ok:true). Read each validation error, fix the JSON, "
        "and submit again — do not end the step with prose only."
    )


__all__ = ["parent_pathway_synth_missing_draft_error"]
