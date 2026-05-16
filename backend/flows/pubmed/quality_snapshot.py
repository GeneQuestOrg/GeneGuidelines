"""Extract compact quality metadata from pubmed flow node_outputs for API/UI."""
from __future__ import annotations

from typing import Any

_MAX_ISSUES = 12
_MAX_INSTRUCTION_CHARS = 2000


def extract_pubmed_quality_snapshot(node_outputs: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return pm_eval / pm_fix summary when present."""
    if not isinstance(node_outputs, dict):
        return None
    eval_out = node_outputs.get("pm_eval")
    fix_out = node_outputs.get("pm_fix")
    if not isinstance(eval_out, dict) and not isinstance(fix_out, dict):
        return None

    snapshot: dict[str, Any] = {}
    if isinstance(eval_out, dict):
        issues = eval_out.get("issues") if isinstance(eval_out.get("issues"), list) else []
        snapshot["pm_eval"] = {
            "ok": eval_out.get("ok"),
            "issues_found": bool(eval_out.get("issues_found")),
            "quality_summary": str(eval_out.get("quality_summary") or "").strip(),
            "correction_instructions": str(eval_out.get("correction_instructions") or "")[
                :_MAX_INSTRUCTION_CHARS
            ],
            "issues": issues[:_MAX_ISSUES],
            "issue_count": len(issues),
        }
    if isinstance(fix_out, dict):
        snapshot["pm_fix"] = {
            "applied": bool(str(fix_out.get("guideline_html") or "").strip()),
            "disease_name": str(fix_out.get("disease_name") or "").strip(),
        }
    retry = node_outputs.get("pm-targeted-retry")
    if isinstance(retry, dict) and retry.get("retry_performed"):
        snapshot["targeted_retry"] = {
            "retried_sections": retry.get("retried_sections") or [],
            "planned_retry_count": retry.get("planned_retry_count"),
        }
    return snapshot or None
