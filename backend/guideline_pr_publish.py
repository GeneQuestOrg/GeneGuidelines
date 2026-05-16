"""Apply approved guideline PRs to the living guideline document (sections_json)."""
from __future__ import annotations

import copy
from datetime import date
from typing import Any

try:
    from .content_db import _load_pr_paragraph_map
except ImportError:
    from content_db import _load_pr_paragraph_map


class GuidelinePrPublishError(ValueError):
    """Raised when a PR cannot be published to the guideline document."""


def _today_iso() -> str:
    return date.today().isoformat()


def _finalize_paragraph(p: dict[str, Any], *, reviewer: str, pr_id: str, on_date: str) -> dict[str, Any]:
    out = copy.deepcopy(p)
    out.pop("prInDiff", None)
    out["lastChange"] = {
        "type": "verified",
        "by": reviewer,
        "date": on_date,
        "prId": pr_id,
    }
    return out


def apply_pr_to_guideline_document(
    document: dict[str, Any],
    *,
    para_map: dict[str, Any],
    pr_id: str,
    reviewer: str,
) -> dict[str, Any]:
    """Return a new document dict with PR changes merged into the target section."""
    if not para_map:
        raise GuidelinePrPublishError(
            f"PR {pr_id} has no paragraphMap — add an entry in content_pr_para_maps.json before publishing."
        )

    target_section = str(para_map.get("targetSection") or "").strip()
    if not target_section:
        raise GuidelinePrPublishError(f"PR {pr_id} paragraphMap.targetSection is empty.")

    mode = str(para_map.get("replaceMode") or "").strip()
    target_ids = {str(x) for x in (para_map.get("targetParaIds") or [])}
    on_date = _today_iso()
    doc = copy.deepcopy(document)
    sections = doc.get("sections")
    if not isinstance(sections, list):
        raise GuidelinePrPublishError("Guideline document has no sections array.")

    section = next((s for s in sections if isinstance(s, dict) and s.get("id") == target_section), None)
    if section is None:
        raise GuidelinePrPublishError(
            f"Section '{target_section}' not found in guideline document for PR {pr_id}."
        )

    paragraphs = section.get("paragraphs")
    if not isinstance(paragraphs, list):
        raise GuidelinePrPublishError(f"Section '{target_section}' has no paragraphs.")

    if mode == "already-applied":
        section["paragraphs"] = [
            _finalize_paragraph(p, reviewer=reviewer, pr_id=pr_id, on_date=on_date)
            if isinstance(p, dict) and p.get("id") in target_ids
            else p
            for p in paragraphs
            if isinstance(p, dict)
        ]
        return doc

    if mode == "insert-after":
        insert_after = str(para_map.get("insertAfter") or "").strip()
        added = para_map.get("addedParagraph")
        if not insert_after or not isinstance(added, dict):
            raise GuidelinePrPublishError(
                f"PR {pr_id} insert-after publish requires insertAfter and addedParagraph."
            )
        added_id = str(added.get("id") or "").strip()
        if not added_id:
            raise GuidelinePrPublishError(f"PR {pr_id} addedParagraph.id is required.")

        has_added_in_doc = any(
            isinstance(x, dict) and x.get("id") == added_id for x in paragraphs
        )
        new_paras: list[Any] = []
        found_anchor = False
        for p in paragraphs:
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            if pid == added_id:
                new_paras.append(
                    _finalize_paragraph(p, reviewer=reviewer, pr_id=pr_id, on_date=on_date)
                )
                continue
            new_paras.append(p)
            if pid == insert_after:
                found_anchor = True
                if not has_added_in_doc:
                    new_paras.append(
                        _finalize_paragraph(
                            added,
                            reviewer=reviewer,
                            pr_id=pr_id,
                            on_date=on_date,
                        )
                    )
        if not found_anchor:
            raise GuidelinePrPublishError(
                f"PR {pr_id}: anchor paragraph '{insert_after}' not found in section."
            )
        section["paragraphs"] = new_paras
        return doc

    if mode == "replace":
        merged: list[Any] = []
        for p in paragraphs:
            if not isinstance(p, dict):
                continue
            pr_diff = p.get("prInDiff") if isinstance(p.get("prInDiff"), dict) else {}
            if pr_diff.get("prId") == pr_id and pr_diff.get("removed") is True:
                continue
            if p.get("id") in target_ids:
                if pr_diff.get("added") is True or p.get("id") in target_ids:
                    merged.append(_finalize_paragraph(p, reviewer=reviewer, pr_id=pr_id, on_date=on_date))
                continue
            merged.append(p)
        if not merged:
            raise GuidelinePrPublishError(f"PR {pr_id} replace would remove all paragraphs in section.")
        section["paragraphs"] = merged
        return doc

    raise GuidelinePrPublishError(
        f"PR {pr_id} has unsupported replaceMode '{mode}'. "
        "Use replace, insert-after, or already-applied."
    )


def publish_pr_to_stored_document(
    document: dict[str, Any],
    *,
    pr_id: str,
    reviewer: str,
) -> dict[str, Any]:
    """Merge PR using paragraph map file; returns updated document."""
    para_map = _load_pr_paragraph_map(pr_id)
    if para_map is None:
        raise GuidelinePrPublishError(
            f"No paragraphMap for {pr_id}. Add it to backend/content_pr_para_maps.json."
        )
    return apply_pr_to_guideline_document(
        document,
        para_map=para_map,
        pr_id=pr_id,
        reviewer=reviewer,
    )
