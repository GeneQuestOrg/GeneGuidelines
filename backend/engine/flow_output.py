from __future__ import annotations

import json
from typing import Any

# Canonical PubMed guideline JSON for API/UI — repair step must win over assembled draft.
_PUBMED_GUIDELINE_NODE_PRIORITY: tuple[str, ...] = ("pm_fix", "pm-4", "pm-4-build", "pm-merge")


def unwrap_node_output_payload(raw: Any) -> dict[str, Any]:
    """Return the business payload from a stored node output."""
    if isinstance(raw, dict) and isinstance(raw.get("result"), dict):
        return raw.get("result") or {}
    return raw if isinstance(raw, dict) else {}


def _is_useful_pubmed_guideline_payload(payload: dict[str, Any]) -> bool:
    """True if this node output looks like a full structured guideline (not rubric-only)."""
    if not payload:
        return False
    gh = str(payload.get("guideline_html") or "").strip()
    if len(gh) >= 50:
        return True
    disease = str(payload.get("disease_name") or "").strip()
    if len(gh) >= 12 and (
        disease
        or payload.get("article_count") is not None
        or payload.get("confidence_index") is not None
        or payload.get("evidence_score") is not None
    ):
        return True
    sh = str(payload.get("section_html") or "").strip()
    if len(sh) >= 50:
        return True
    return bool(disease and payload.get("article_count") is not None)


def pick_pubmed_canonical_payload(node_outputs: dict[str, Any]) -> dict[str, Any]:
    """Prefer repaired guideline (pm_fix) over raw synthesis (pm-4) over merge build (pm-4-build)."""
    if not isinstance(node_outputs, dict):
        return {}
    for nid in _PUBMED_GUIDELINE_NODE_PRIORITY:
        payload = unwrap_node_output_payload(node_outputs.get(nid))
        if _is_useful_pubmed_guideline_payload(payload):
            return payload
    return {}


def derive_flow_output_from_node_outputs(flow_key: str, node_outputs: dict[str, Any]) -> str:
    """Build a stable fallback output when store['output'] is empty."""
    if not isinstance(node_outputs, dict) or not node_outputs:
        return ""

    if flow_key == "parent_pathway":
        picked = pick_parent_pathway_canonical_payload(node_outputs)
        if picked:
            try:
                return json.dumps(picked, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(picked)

    if flow_key == "pubmed":
        picked = pick_pubmed_canonical_payload(node_outputs)
        if picked:
            try:
                return json.dumps(picked, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(picked)

    for node_id in (
        "end",
        "final",
        "output",
        "close",
        "pm-5",
        "pm-4-build",
        "pm-merge",
    ):
        payload = unwrap_node_output_payload(node_outputs.get(node_id))
        if payload:
            try:
                return json.dumps(payload, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(payload)
    return ""


def pick_parent_pathway_canonical_payload(node_outputs: dict[str, Any]) -> dict[str, Any]:
    """Prefer pp-end output, then any node with pathway key."""
    if not isinstance(node_outputs, dict):
        return {}
    for nid in ("pp-end", "pp-synth", "pp-load"):
        payload = unwrap_node_output_payload(node_outputs.get(nid))
        if isinstance(payload, dict) and payload.get("pathway"):
            return payload
        if isinstance(payload, dict) and payload.get("ok") and payload.get("tree"):
            return {"ok": True, "pathway": {"tree": payload["tree"]}}
    return {}


def finalize_flow_output(flow_key: str, store: dict[str, Any]) -> None:
    """Pick the canonical flow output for SSE and API consumers."""
    node_outputs = store.get("node_outputs") or {}
    if flow_key == "parent_pathway":
        picked = pick_parent_pathway_canonical_payload(node_outputs)
        if picked:
            try:
                store["output"] = json.dumps(picked, ensure_ascii=False)
                return
            except (TypeError, ValueError):
                store["output"] = str(picked)
                return
    if flow_key == "pubmed":
        picked = pick_pubmed_canonical_payload(node_outputs)
        if picked:
            if picked.get("guideline_html") and not picked.get("section_html"):
                picked = {**picked, "section_html": picked["guideline_html"]}
            try:
                store["output"] = json.dumps(picked, ensure_ascii=False)
                return
            except (TypeError, ValueError):
                store["output"] = str(picked)
                return
    if not str(store.get("output") or "").strip():
        store["output"] = derive_flow_output_from_node_outputs(flow_key, node_outputs)
