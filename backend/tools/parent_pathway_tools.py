"""MCP tools for patient-facing care pathway (chart) generation."""
from __future__ import annotations

import json
from typing import Any


def _json_ok(result: Any, *, message: str = "ok") -> str:
    return json.dumps(
        {"ok": True, "status": "success", "message": message, "result": result, "errors": [], "missing": []},
        ensure_ascii=False,
    )


def _json_err(message: str, *, missing: list[str] | None = None, errors: list[str] | None = None) -> str:
    return json.dumps(
        {
            "ok": False,
            "status": "error",
            "message": message,
            "result": None,
            "errors": errors or [message],
            "missing": missing or [],
        },
        ensure_ascii=False,
    )


def register_parent_pathway_tools(mcp: Any) -> None:
    """Register pathway MCP tools on the server instance."""

    @mcp.tool()
    def get_parent_pathway_context(disease_slug: str) -> str:
        """
        Load published guideline excerpts and allowed PMIDs for patient chart synthesis.
        Call before building a decision tree. Requires an existing guideline document.
        """
        slug = (disease_slug or "").strip().lower()
        if not slug:
            return _json_err("disease_slug is required", missing=["disease_slug"])
        try:
            from backend.flows.parent_pathway.context import load_pathway_context
        except ImportError:
            from flows.parent_pathway.context import load_pathway_context

        payload = load_pathway_context(slug)
        if not payload.get("ok"):
            return _json_err(str(payload.get("error") or "Failed to load context"))
        return _json_ok(payload, message="parent_pathway_context loaded")

    @mcp.tool()
    def validate_parent_pathway_json(pathway_json: str, disease_slug: str = "") -> str:
        """
        Validate a parent decision-tree JSON object without saving.
        When disease_slug is set, PMIDs must appear in the published guideline.
        """
        raw = (pathway_json or "").strip()
        if not raw:
            return _json_err("pathway_json is required", missing=["pathway_json"])
        slug = (disease_slug or "").strip().lower()
        guideline_doc = None
        if slug:
            try:
                from backend.content_db import get_guideline_document
            except ImportError:
                from content_db import get_guideline_document
            guideline_doc = get_guideline_document(slug)
        try:
            from backend.parent_pathway_schema import (
                ParentPathwayValidationError,
                validate_parent_pathway_json as validate_fn,
            )
        except ImportError:
            from parent_pathway_schema import (
                ParentPathwayValidationError,
                validate_parent_pathway_json as validate_fn,
            )
        try:
            tree, warnings = validate_fn(raw, guideline_document=guideline_doc)
        except ParentPathwayValidationError as exc:
            return _json_err(str(exc))
        return _json_ok({"tree": tree, "warnings": warnings}, message="pathway valid")

    @mcp.tool()
    def submit_parent_pathway(
        disease_slug: str,
        pathway_json: str,
        locale: str = "en",
        based_on: str = "",
        source_execution_id: str = "",
    ) -> str:
        """
        Validate and save a patient-facing pathway chart (decision tree) for a disease.
        pathway_json must follow the schema: root with children[] of decision/action nodes.
        """
        slug = (disease_slug or "").strip().lower()
        if not slug:
            return _json_err("disease_slug is required", missing=["disease_slug"])
        raw = (pathway_json or "").strip()
        if not raw:
            return _json_err("pathway_json is required", missing=["pathway_json"])
        try:
            from backend.content_db import get_guideline_document, get_guideline_meta, save_parent_pathway
            from backend.parent_pathway_schema import (
                ParentPathwayValidationError,
                validate_parent_pathway_json,
            )
        except ImportError:
            from content_db import get_guideline_document, get_guideline_meta, save_parent_pathway
            from parent_pathway_schema import (
                ParentPathwayValidationError,
                validate_parent_pathway_json,
            )

        doc = get_guideline_document(slug)
        if doc is None:
            return _json_err(
                "No published guideline for this disease — generate and publish a guideline first."
            )
        try:
            tree, warnings = validate_parent_pathway_json(raw, guideline_document=doc)
        except ParentPathwayValidationError as exc:
            return _json_err(str(exc))
        meta = get_guideline_meta(slug) or {}
        based = (based_on or "").strip() or str(doc.get("basedOn") or "")
        saved = save_parent_pathway(
            slug,
            tree,
            version="v1.0-ai",
            based_on=based,
            locale=(locale or "en").strip()[:2] or "en",
            source_guideline_version=str(meta.get("version") or ""),
            source_execution_id=(source_execution_id or "").strip() or None,
        )
        return _json_ok(
            {
                "disease_slug": slug,
                "version": saved.get("version"),
                "warnings": warnings,
            },
            message="Patient pathway saved as draft — publish from admin when ready",
        )
