"""Executor for evaluation_check — second-pass QA on generated synthesis vs reference facts."""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from .base import FlowRuntimeBundle, NodeExecutor, NodeInput, NodeOutput

log = logging.getLogger(__name__)

_EVALUATION_MAX_SYNTHESIS_CHARS = 120_000
_EVALUATION_MAX_REFERENCE_CHARS = 24_000

_SYSTEM_HEAD = (
    "You are a clinical quality reviewer. Compare SYNTHESIS against REFERENCE_FACTS. "
    "Flag only inconsistencies verifiable from those two inputs; do not invent clinical facts. "
    "Priorities: "
    "(1) Cross-section consistency — the same drug, dose or schedule, trial primary endpoint/outcome, epidemiology figure, or safety claim must not contradict across headings or HTML sections; when it does, flag it and name both locations (snippet or section title). "
    "(2) Numeric and unit coherence — incompatible prevalence, incidence, dosing amounts, or calendar intervals across sections count even if language is hedged ('may', 'approximately'). "
    "(3) PMID and citation hygiene — typical PubMed IDs are 7–8 digits in a plausible range; flag clearly invalid digit lengths or non-PubMed-looking IDs presented as PubMed articles. Flag geography, registry, or study-design claims that contradict REFERENCE_FACTS. "
    "(4) Internal clinical contradictions — e.g. a contraindication in one section vs a recommendation elsewhere. "
    "(5) Meta-text leaks — any assistant/planning prose visible in the guideline (e.g. 'I will now', 'pass1 synthesis', 'I cannot see') is always high severity. "
    "Each issue must include an actionable suggested_fix: one harmonized stance supported by REFERENCE_FACTS, or explicit downgrade to conditional/unknown wording when evidence is insufficient. "
    "Respond using the structured schema only. English in schema fields; issue messages may quote Polish fragments from SYNTHESIS."
)


class EvaluationIssue(BaseModel):
    """Single inconsistency flagged for downstream correction."""

    code: str = Field(..., min_length=2, max_length=64)
    severity: str = Field(..., min_length=3, max_length=16)
    message: str = Field(..., min_length=3, max_length=4000)
    location: str = Field(default="", max_length=800)
    suggested_fix: str = Field(default="", max_length=8000)


class EvaluationStructured(BaseModel):
    """Structured LLM output for evaluation_check."""

    issues_found: bool
    issues: list[EvaluationIssue] = Field(default_factory=list)
    correction_instructions: str = Field(default="", max_length=16000)
    quality_summary: str = Field(default="", max_length=6000)


def _parse_source_node_ids(node_config: dict[str, Any]) -> list[str]:
    raw = (node_config.get("evaluation_source_nodes_json") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                out = [x.strip() for x in parsed if x.strip()]
                if out:
                    return out
        except json.JSONDecodeError:
            log.warning("evaluation_check: invalid evaluation_source_nodes_json, using default")
    return ["pm-4-build", "pm-5-repair"]


def _extract_text_from_node_blob(blob: Any) -> str:
    """Pull human-readable synthesis text from a node output dict."""
    if not isinstance(blob, dict):
        return ""
    text = (blob.get("output_text") or blob.get("cleaned_text") or "").strip()
    if text:
        return text
    result = blob.get("result")
    if isinstance(result, dict):
        parts: list[str] = []
        for key in (
            "guideline_html",
            "recommendation_matrix_html",
            "red_flags_html",
            "contraindications_html",
            "follow_up_schedule_html",
            "evidence_gaps_html",
            "disclaimer_html",
            "reliability_assessment_html",
            "source_links_html",
            "section_html",
        ):
            chunk = result.get(key)
            if isinstance(chunk, str) and chunk.strip():
                parts.append(chunk.strip())
        refs = result.get("references")
        if isinstance(refs, str) and refs.strip():
            parts.append(refs.strip())
        if parts:
            return "\n\n".join(parts)
        inner = (result.get("output_html") or result.get("output_text") or "").strip()
        if inner:
            return inner
    elif isinstance(result, str) and result.strip():
        return result.strip()

    gh = blob.get("guideline_html")
    if isinstance(gh, str) and gh.strip():
        return gh.strip()
    try:
        return json.dumps(blob, ensure_ascii=False)[:50_000]
    except Exception:
        return str(blob)[:50_000]


def _gather_synthesis(context: dict[str, Any], source_ids: list[str]) -> tuple[str, list[str]]:
    missing: list[str] = []
    chunks: list[str] = []
    for nid in source_ids:
        blob = context.get(nid)
        chunk = _extract_text_from_node_blob(blob)
        if chunk.strip():
            chunks.append(f"--- node {nid} ---\n{chunk}")
        else:
            missing.append(nid)
    return "\n\n".join(chunks), missing


def _reference_facts_bundle(context: dict[str, Any]) -> str:
    """Compact factual anchor text derived from deterministic retrieval stages."""
    lines: list[str] = []
    pm2 = context.get("pm-2") or {}
    res2 = pm2.get("result") if isinstance(pm2.get("result"), dict) else pm2 if isinstance(pm2, dict) else {}
    if isinstance(res2, dict):
        qt = str(res2.get("query_text") or "").strip()
        if qt:
            lines.append(f"query_text: {qt}")
        lines.append(f"article_count: {res2.get('article_count', '')}")
        lines.append(f"total_analyzed: {res2.get('total_analyzed', '')}")
        art_text = str(res2.get("articles_text") or "").strip()
        if art_text:
            snippet = art_text[:_EVALUATION_MAX_REFERENCE_CHARS]
            lines.append("articles_text (truncated):\n" + snippet)

    pm1 = context.get("pm-1") or {}
    r1 = pm1.get("result") if isinstance(pm1.get("result"), dict) else pm1 if isinstance(pm1, dict) else {}
    if isinstance(r1, dict):
        up = r1.get("unique_pmids") or r1.get("pmids") or []
        if isinstance(up, list) and up:
            lines.append("unique_pmids (sample): " + ", ".join(str(x) for x in up[:40]))

    for key in ("pmid_verify", "pm-verify"):
        pv = context.get(key)
        if isinstance(pv, dict) and pv.get("summary"):
            lines.append(f"{key}.summary: {pv.get('summary')}")
            break

    out = "\n".join(lines)
    if len(out) > _EVALUATION_MAX_REFERENCE_CHARS:
        return out[:_EVALUATION_MAX_REFERENCE_CHARS] + "\n…(truncated)…"
    return out


def _normalize_payload(raw: dict[str, Any]) -> dict[str, Any]:
    issues_raw = raw.get("issues") if isinstance(raw.get("issues"), list) else []
    norm_issues: list[dict[str, Any]] = []
    for item in issues_raw:
        if not isinstance(item, dict):
            continue
        try:
            ei = EvaluationIssue.model_validate(item)
            norm_issues.append(ei.model_dump())
        except Exception:
            continue
    issues_found = bool(raw.get("issues_found")) and len(norm_issues) > 0
    if norm_issues:
        issues_found = True
    return {
        "ok": True,
        "issues_found": issues_found,
        "issues": norm_issues,
        "correction_instructions": str(raw.get("correction_instructions") or "").strip(),
        "quality_summary": str(raw.get("quality_summary") or "").strip(),
    }


class EvaluationCheckExecutor(NodeExecutor):
    """Runs a structured LLM pass to flag inconsistencies; does not rewrite user-facing HTML."""

    @classmethod
    def node_type(cls) -> str:
        return "evaluation_check"

    async def execute(self, input: NodeInput) -> NodeOutput:
        bundle = input.flow_runtime
        if not isinstance(bundle, FlowRuntimeBundle):
            return NodeOutput(
                data={
                    "ok": False,
                    "error": "evaluation_check requires flow_runtime (internal wiring bug).",
                    "issues_found": True,
                    "issues": [
                        {
                            "code": "EVAL_INTERNAL",
                            "severity": "high",
                            "message": "Evaluation node was executed without engine runtime context.",
                            "location": "",
                            "suggested_fix": "Redeploy backend or report this as a bug.",
                        }
                    ],
                    "correction_instructions": "",
                    "quality_summary": "",
                }
            )

        node = input.node_config
        node_id = str(node.get("node_id") or "evaluation_check")

        emit_fn = bundle.emit_fn
        if emit_fn is None:
            emit_fn = lambda _q, _e: None

        sources = _parse_source_node_ids(node)
        synthesis, missing_sources = _gather_synthesis(input.context or {}, sources)
        reference = _reference_facts_bundle(input.context or {})

        extra_rules = str(node.get("prompt") or "").strip()
        system = _SYSTEM_HEAD + ("\n\nAuthor instructions:\n" + extra_rules if extra_rules else "")

        if not synthesis.strip():
            msg = "No synthesis text found for evaluation."
            if missing_sources:
                msg += " Missing content from: " + ", ".join(missing_sources)
            return NodeOutput(
                data={
                    "ok": True,
                    "issues_found": True,
                    "issues": [
                        {
                            "code": "MISSING_SYNTHESIS",
                            "severity": "high",
                            "message": msg,
                            "location": ",".join(sources),
                            "suggested_fix": "Ensure upstream nodes produced guideline_html or output_text.",
                        }
                    ],
                    "correction_instructions": "Restore upstream synthesis output, then rerun evaluation.",
                    "quality_summary": "Evaluation skipped — empty synthesis.",
                    "evaluation_sources": sources,
                    "missing_sources": missing_sources,
                }
            )

        synthesis_truncated = synthesis[:_EVALUATION_MAX_SYNTHESIS_CHARS]
        if len(synthesis) > _EVALUATION_MAX_SYNTHESIS_CHARS:
            synthesis_truncated += "\n…(truncated for evaluation context)…"

        user_prompt = (
            "REFERENCE_FACTS:\n"
            f"{reference}\n\n"
            "SYNTHESIS:\n"
            f"{synthesis_truncated}\n"
        )

        from ..agents.simple_runner import (
            resolve_max_tokens_for_node,
            resolve_model_spec_for_node,
            run_llm_simple_async,
        )

        model_spec = resolve_model_spec_for_node(node)
        max_tokens = min(resolve_max_tokens_for_node(node), 16_000)
        try:
            max_retry = int(node.get("max_retry") or 2)
        except (TypeError, ValueError):
            max_retry = 2

        raw = await run_llm_simple_async(
            system_prompt=system,
            user_prompt=user_prompt,
            result_type=EvaluationStructured,
            model_spec=model_spec,
            max_tokens=max_tokens,
            max_retry=max_retry,
            store=bundle.store,
            event_queue=bundle.event_queue,
            node_id=node_id,
            emit_fn=emit_fn,
            poison_store_on_failure=False,
            sse_kind="llm_evaluation",
        )

        if not raw:
            return NodeOutput(
                data={
                    "ok": False,
                    "issues_found": True,
                    "issues": [
                        {
                            "code": "EVALUATION_FAILED",
                            "severity": "high",
                            "message": "Structured evaluation LLM returned no output after retries.",
                            "location": node_id,
                            "suggested_fix": "Retry the flow; if this persists, check API keys and model availability.",
                        }
                    ],
                    "correction_instructions": "Manually review synthesis; rerun evaluation after fixing connectivity.",
                    "quality_summary": "Evaluation LLM failed.",
                    "evaluation_sources": sources,
                    "missing_sources": missing_sources,
                }
            )

        merged = _normalize_payload(raw)
        merged["evaluation_sources"] = sources
        merged["missing_sources"] = missing_sources
        return NodeOutput(data=merged)
