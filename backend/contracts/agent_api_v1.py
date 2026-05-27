from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field


AGENT_API_CONTRACT_VERSION = "v1"

AgentTraceKind = Literal[
    "sys",
    "ai_summary",
    "diagnostic",
    "ticket_status",
    "missing_tool_request",
    "output",
    "technician_steps",
]


class AgentRunPayload(TypedDict):
    contract_version: str
    execution_id: str
    ticket_id: int
    done: bool
    error: str | None
    output: str | None
    structured_output: dict[str, Any] | None
    quality_snapshot: dict[str, Any] | None
    ai_summary: dict[str, Any]
    diagnostics_entries: list[Any]
    steps_completed_by_ai: list[Any]
    missing_tool_requests: list[Any]
    current_stage: str | None


def normalize_trace_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict(event or {})
    kind = str(payload.get("kind") or "").strip()
    if not kind and not payload.get("done"):
        payload["kind"] = "sys"
    return payload


def _resolve_quality_snapshot(run: dict[str, Any]) -> dict[str, Any] | None:
    snap = run.get("quality_snapshot")
    if isinstance(snap, dict):
        return snap
    if str(run.get("flow_key") or "") != "pubmed":
        return None
    try:
        from ..flows.pubmed.quality_snapshot import extract_pubmed_quality_snapshot
    except ImportError:
        from flows.pubmed.quality_snapshot import extract_pubmed_quality_snapshot

    return extract_pubmed_quality_snapshot(run.get("node_outputs") or {})


def build_agent_run_payload(run: dict[str, Any]) -> AgentRunPayload:
    output = run.get("output")
    if not str(output or "").strip() and str(run.get("flow_key") or "") == "pubmed":
        try:
            from ..engine.flow_output import pick_pubmed_canonical_payload
        except ImportError:
            from engine.flow_output import pick_pubmed_canonical_payload

        picked = pick_pubmed_canonical_payload(run.get("node_outputs") or {})
        if picked:
            import json

            output = json.dumps(picked, ensure_ascii=False)

    return AgentRunPayload(
        contract_version=AGENT_API_CONTRACT_VERSION,
        execution_id=str(run.get("execution_id") or ""),
        ticket_id=int(run.get("ticket_id") or 0),
        done=bool(run.get("done", False)),
        error=run.get("error"),
        output=output,
        structured_output=run.get("structured_output"),
        quality_snapshot=_resolve_quality_snapshot(run),
        ai_summary=run.get("ai_summary") or {"issue": "", "work_log_summary": ""},
        diagnostics_entries=run.get("diagnostics_entries") or [],
        steps_completed_by_ai=run.get("steps_completed_by_ai") or [],
        missing_tool_requests=run.get("missing_tool_requests") or [],
        current_stage=str(run.get("current_stage") or run.get("last_stage") or "").strip() or None,
    )


TopicBucket = Literal[
    "pathogenesis",
    "diagnostics",
    "treatment",
    "follow_up",
    "general",
]


class PubmedArticle(BaseModel):
    """Single PubMed article payload forwarded from pm-1 agent to pm-2 normalizer."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    pmid: str = Field(..., min_length=1)
    title: str = ""
    authors: str = ""
    source: str = ""
    pubdate: str = ""
    doi: str = ""
    abstract: str = ""
    pubmed_url: str = ""
    doi_url: str = ""
    topic_bucket: TopicBucket = "general"
    pubtype: list[str] = Field(default_factory=list)
    evidence_tier: int = 6
    evidence_tier_label: str = ""


class PubmedEvidenceCard(BaseModel):
    """Curation note linking a PMID to a bucket with inclusion rationale."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    pmid: str = Field(..., min_length=1)
    topic_bucket: TopicBucket = "general"
    inclusion_reason: str = ""
    confidence: Literal["very_low", "low", "moderate", "medium", "high"] = "medium"
    title: str = ""
    pubdate: str = ""
    source: str = ""
    pubtype: list[str] = Field(default_factory=list)
    evidence_tier: int = 6
    evidence_tier_label: str = ""


class PubmedRetrievalContract(BaseModel):
    """Structured final output for agentic pm-1 node.

    Forces the LLM to emit a parseable JSON shape with articles[] so pm-2 can
    normalize it deterministically. Extra fields are tolerated to keep the
    prompt forward-compatible.
    """

    model_config = ConfigDict(extra="ignore")

    query_text: str
    query_variants: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    total_found_estimate: int = 0
    total_requested: int = 0
    total_analyzed: int = 0
    total_with_abstract: int = 0
    articles: list[PubmedArticle] = Field(default_factory=list)
    evidence_cards: list[PubmedEvidenceCard] = Field(default_factory=list)


AGENTIC_OUTPUT_CONTRACTS: dict[str, type[BaseModel]] = {
    "pm-1": PubmedRetrievalContract,
}


def get_agentic_output_contract(node_id: str) -> type[BaseModel] | None:
    """Return the Pydantic contract class to enforce on an agentic node, if any."""
    return AGENTIC_OUTPUT_CONTRACTS.get(node_id)
