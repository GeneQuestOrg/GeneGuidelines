"""Validate and normalize parent care pathway decision trees."""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .contracts.parent_pathway_v1 import (
    MAX_ACTION_TITLE_LEN,
    MAX_ANSWER_LEN,
    MAX_DECISION_TITLE_LEN,
    MAX_HINT_LEN,
    MAX_NODE_COUNT,
    MAX_QUESTION_LEN,
    MAX_SPECIALTY_LEN,
    MAX_ABOUT_SUMMARY_LEN,
    MAX_ABOUT_TITLE_LEN,
    MAX_SUBTITLE_LEN,
    MAX_TOP_LEVEL_CHILDREN,
    MAX_TREE_DEPTH,
    MAX_WHAT_TO_EXPECT_LEN,
    MIN_ABOUT_SUMMARY_LEN,
    MIN_ACTION_QUESTION_COUNT,
    MIN_ACTION_WHAT_TO_EXPECT_LEN,
    MIN_TOP_LEVEL_ACTION_STEPS,
)

_PMID_RE = re.compile(r"^\d{7,9}$")

_COLD_QUESTION_PATTERNS = re.compile(
    r"\b("
    r"MRI|OCT|optic|canal|bisphosphonate|denosumab|histolog|somatic|"
    r"monitoring|involvement|McCune|MAS|temporal bone|decompression|"
    r"clinical trial|long-term risk|resection|orthognathic"
    r")\b",
    re.IGNORECASE,
)

# Titles that look like LLM placeholders — families need concrete visit themes.
_HOLLOW_ACTION_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^concrete\s+step\b", re.IGNORECASE),
    re.compile(r"^step\s*\d+\s*$", re.IGNORECASE),
    re.compile(r"^(first|second|third|fourth|next)\s+step\b", re.IGNORECASE),
    re.compile(r"^next\s+steps?\s*\d", re.IGNORECASE),
)


def _collapse_ws_lower(value: str) -> str:
    return " ".join(str(value).split()).strip().lower()


def _validate_action_steps_distinct_and_concrete(top_actions: list[dict]) -> None:
    """Reject copy-paste checklists: same title, same expectations, or one vague role repeated."""
    if len(top_actions) < 2:
        return

    titles = [_collapse_ws_lower(str(s.get("title") or "")) for s in top_actions]
    if any(not t for t in titles):
        raise ParentPathwayValidationError("Every action step needs a specific, non-empty title.")
    if len(set(titles)) < len(titles):
        raise ParentPathwayValidationError(
            "Two or more steps share the same title — rewrite so each line names a different visit or task "
            "(for example: gathering records vs genetics vs a bone or pain clinic vs when to call urgently)."
        )

    expects = [_collapse_ws_lower(str(s.get("whatToExpect") or "")) for s in top_actions]
    if len(set(expects)) < len(expects):
        raise ParentPathwayValidationError(
            "Steps repeat the same whatToExpect text — each step must describe a different visit or phone "
            "call, not copy-pasted boilerplate."
        )

    specs = [_collapse_ws_lower(str(s.get("specialty") or "")) for s in top_actions]
    if len(set(specs)) < 2:
        raise ParentPathwayValidationError(
            "Use at least two different plain-language roles across the chart (for example GP, genetics, "
            "orthopedics, endocrinology, nurse coordinator) — not the same specialty line on every step."
        )

    for step in top_actions:
        sid = str(step.get("id") or "?")
        raw_title = str(step.get("title") or "").strip()
        for pat in _HOLLOW_ACTION_TITLE_PATTERNS:
            if pat.search(raw_title):
                raise ParentPathwayValidationError(
                    f"Step {sid}: title looks like a placeholder ({raw_title!r}). "
                    "Name the real-world task (e.g. 'Collect imaging and clinic letters before genetics')."
                )

    q_sets: list[tuple[str, ...]] = []
    for step in top_actions:
        raw_qs = step.get("questions") or []
        if not isinstance(raw_qs, list):
            continue
        fp = tuple(sorted(_collapse_ws_lower(str(q)) for q in raw_qs if str(q).strip()))
        q_sets.append(fp)
    if len(q_sets) == len(top_actions) and len(set(q_sets)) < len(q_sets):
        raise ParentPathwayValidationError(
            "Two steps reuse the same question list — write different questions families can ask at each visit."
        )


class ParentPathwayValidationError(ValueError):
    """Raised when a pathway tree fails structural or evidence rules."""


class PathwayBranchModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(..., min_length=1, max_length=MAX_ANSWER_LEN)
    next: "PathwayNodeModel | None" = None


class PathwayNodeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1)
    action: bool = False
    hint: str | None = None
    branches: list[PathwayBranchModel] | None = None
    urgent: bool = False
    specialty: str | None = None
    whatToExpect: str | None = None
    questions: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    doctorHint: str | None = None
    evidenceGap: bool = False

    @field_validator("id")
    @classmethod
    def id_pattern(cls, value: str) -> str:
        trimmed = value.strip()
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", trimmed):
            raise ValueError("id must be lowercase slug (letters, digits, hyphens)")
        return trimmed


class PathwayAboutModel(BaseModel):
    """Plain-language disease intro for families — shown above next steps."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=MAX_ABOUT_TITLE_LEN)
    summary: str = Field(..., min_length=MIN_ABOUT_SUMMARY_LEN, max_length=MAX_ABOUT_SUMMARY_LEN)


class ParentPathwayTreeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default="root", min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=MAX_DECISION_TITLE_LEN)
    subtitle: str = Field(default="", max_length=MAX_SUBTITLE_LEN)
    about: PathwayAboutModel | None = None
    locale: str = Field(default="en", pattern=r"^[a-z]{2}$")
    basedOn: str = Field(default="", max_length=500)
    sourceRunId: str | None = Field(default=None, max_length=128)
    children: list[PathwayNodeModel] = Field(default_factory=list)


PathwayBranchModel.model_rebuild()


def _collect_pmids_from_guideline(document: dict[str, Any]) -> set[str]:
    pmids: set[str] = set()
    for section in document.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for para in section.get("paragraphs") or []:
            if not isinstance(para, dict):
                continue
            for raw in para.get("citations") or []:
                pmid = str(raw).strip()
                if _PMID_RE.match(pmid):
                    pmids.add(pmid)
    return pmids


def _validate_top_level_patient_chart_richness(normalized: dict[str, Any]) -> None:
    """Reject placeholder trees (e.g. accidental test fixtures) that would not help families."""
    children = normalized.get("children") or []
    if not isinstance(children, list):
        return
    top_actions = [c for c in children if isinstance(c, dict) and c.get("action")]
    if len(top_actions) < MIN_TOP_LEVEL_ACTION_STEPS:
        raise ParentPathwayValidationError(
            f"Patient chart needs at least {MIN_TOP_LEVEL_ACTION_STEPS} top-level action steps "
            f"(plain-language checklist items). Got {len(top_actions)}. "
            "Add concrete, disease-grounded actions families can take (records, key appointments, "
            "who to call, red flags, support)."
        )
    if len(children) != len(top_actions):
        raise ParentPathwayValidationError(
            "Patient chart expects every top-level item to be action: true (a vertical checklist). "
            "Put yes/no branches inside a step, not as top-level siblings."
        )
    for step in top_actions:
        sid = str(step.get("id") or "?")
        wt = str(step.get("whatToExpect") or "").strip()
        if len(wt) < MIN_ACTION_WHAT_TO_EXPECT_LEN:
            raise ParentPathwayValidationError(
                f"Step {sid}: whatToExpect must be at least {MIN_ACTION_WHAT_TO_EXPECT_LEN} characters "
                f"of plain-language guidance (got {len(wt)})."
            )
        raw_qs = step.get("questions") or []
        if not isinstance(raw_qs, list):
            raise ParentPathwayValidationError(f"Step {sid}: questions must be a list.")
        n_q = len([q for q in raw_qs if str(q).strip()])
        if n_q < MIN_ACTION_QUESTION_COUNT:
            raise ParentPathwayValidationError(
                f"Step {sid}: add at least {MIN_ACTION_QUESTION_COUNT} short questions the family can ask "
                f"at the visit (got {n_q})."
            )

    _validate_action_steps_distinct_and_concrete(top_actions)


def _walk_nodes(
    node: dict[str, Any],
    *,
    depth: int,
    seen_ids: set[str],
    node_count: list[int],
    allowed_pmids: set[str],
    warnings: list[str],
) -> None:
    if depth > MAX_TREE_DEPTH:
        raise ParentPathwayValidationError(
            f"Tree exceeds max depth ({MAX_TREE_DEPTH}). Shorten nested branches."
        )
    node_count[0] += 1
    if node_count[0] > MAX_NODE_COUNT:
        raise ParentPathwayValidationError(
            f"Tree exceeds max node count ({MAX_NODE_COUNT}). Split into fewer decision points."
        )

    node_id = str(node.get("id") or "").strip()
    if not node_id:
        raise ParentPathwayValidationError("Every node must have a non-empty id.")
    if node_id in seen_ids:
        raise ParentPathwayValidationError(f"Duplicate node id: {node_id}")
    seen_ids.add(node_id)

    is_action = bool(node.get("action"))
    title = str(node.get("title") or "").strip()
    if not title:
        raise ParentPathwayValidationError(f"Node {node_id}: title is required.")

    if is_action:
        if len(title) > MAX_ACTION_TITLE_LEN:
            raise ParentPathwayValidationError(
                f"Node {node_id}: action title exceeds {MAX_ACTION_TITLE_LEN} characters."
            )
        specialty = str(node.get("specialty") or "").strip()
        if not specialty:
            raise ParentPathwayValidationError(
                f"Node {node_id}: action nodes require specialty."
            )
        if len(specialty) > MAX_SPECIALTY_LEN:
            raise ParentPathwayValidationError(f"Node {node_id}: specialty too long.")
        what = str(node.get("whatToExpect") or "").strip()
        if what and len(what) > MAX_WHAT_TO_EXPECT_LEN:
            raise ParentPathwayValidationError(f"Node {node_id}: whatToExpect too long.")
        questions = node.get("questions") or []
        if not isinstance(questions, list):
            raise ParentPathwayValidationError(f"Node {node_id}: questions must be a list.")
        if len(questions) < 1:
            warnings.append(f"Node {node_id}: action has no parent questions — add at least one.")
        for q in questions:
            qtext = str(q).strip()
            if not qtext:
                continue
            if len(qtext) > MAX_QUESTION_LEN:
                raise ParentPathwayValidationError(f"Node {node_id}: question too long.")
            if _COLD_QUESTION_PATTERNS.search(qtext):
                warnings.append(
                    f"Node {node_id}: question sounds clinical/cold — rewrite for parents: {qtext[:60]}…"
                )
        citations = node.get("citations") or []
        if citations and not isinstance(citations, list):
            raise ParentPathwayValidationError(f"Node {node_id}: citations must be a list.")
        has_citation = False
        for raw in citations:
            pmid = str(raw).strip()
            if not pmid:
                continue
            if not _PMID_RE.match(pmid):
                raise ParentPathwayValidationError(f"Node {node_id}: invalid PMID {pmid!r}.")
            if allowed_pmids is not None and pmid not in allowed_pmids:
                raise ParentPathwayValidationError(
                    f"Node {node_id}: PMID {pmid} not found in source guideline — remove or add evidence."
                )
            has_citation = True
        if not has_citation and not node.get("evidenceGap"):
            node["evidenceGap"] = True
            warnings.append(f"Node {node_id}: no PMID citations — marked evidenceGap.")
        return

    if len(title) > MAX_DECISION_TITLE_LEN:
        raise ParentPathwayValidationError(
            f"Node {node_id}: decision title exceeds {MAX_DECISION_TITLE_LEN} characters."
        )
    hint = node.get("hint")
    if hint is not None and len(str(hint)) > MAX_HINT_LEN:
        raise ParentPathwayValidationError(f"Node {node_id}: hint too long.")
    branches = node.get("branches")
    if not branches:
        raise ParentPathwayValidationError(
            f"Node {node_id}: decision nodes require at least one branch."
        )
    if not isinstance(branches, list):
        raise ParentPathwayValidationError(f"Node {node_id}: branches must be a list.")
    for branch in branches:
        if not isinstance(branch, dict):
            raise ParentPathwayValidationError(f"Node {node_id}: invalid branch object.")
        answer = str(branch.get("answer") or "").strip()
        if not answer:
            raise ParentPathwayValidationError(f"Node {node_id}: branch answer is required.")
        if len(answer) > MAX_ANSWER_LEN:
            raise ParentPathwayValidationError(f"Node {node_id}: branch answer too long.")
        nxt = branch.get("next")
        if nxt is not None:
            if not isinstance(nxt, dict):
                raise ParentPathwayValidationError(f"Node {node_id}: branch next must be object or null.")
            _walk_nodes(
                nxt,
                depth=depth + 1,
                seen_ids=seen_ids,
                node_count=node_count,
                allowed_pmids=allowed_pmids,
                warnings=warnings,
            )


def _format_pydantic_validation_error(exc: ValidationError) -> str:
    """Short, agent-actionable summary of schema mismatches."""
    parts: list[str] = []
    for err in exc.errors()[:10]:
        loc = ".".join(str(x) for x in err.get("loc") or ())
        msg = str(err.get("msg") or "invalid")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) if parts else "fix required fields and retry."


def coerce_pathway_tree_object(data: Any) -> dict[str, Any]:
    """Normalize common LLM wrapper shapes to the root tree object.

    Accepts the tree at the top level or under ``root``, ``tree``, or ``pathway``.
    """
    if not isinstance(data, dict):
        raise ParentPathwayValidationError("Pathway must be a JSON object.")

    if "children" in data and ("title" in data or str(data.get("id") or "") == "root"):
        return data

    for key in ("root", "tree"):
        inner = data.get(key)
        if isinstance(inner, dict):
            return coerce_pathway_tree_object(inner)

    pathway = data.get("pathway")
    if isinstance(pathway, dict):
        return coerce_pathway_tree_object(pathway)

    return data


def validate_parent_pathway_tree(
    tree: dict[str, Any],
    *,
    allowed_pmids: set[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Parse, structurally validate, and return normalized tree + warnings."""
    tree = coerce_pathway_tree_object(tree)
    try:
        model = ParentPathwayTreeModel.model_validate(tree)
    except ValidationError as exc:
        raise ParentPathwayValidationError(
            f"Pathway JSON does not match schema — {_format_pydantic_validation_error(exc)}"
        ) from exc

    normalized = model.model_dump(mode="json", exclude_none=True)
    warnings: list[str] = []
    seen_ids: set[str] = set()
    node_count = [0]

    if str(normalized.get("id") or "") in seen_ids:
        raise ParentPathwayValidationError("Duplicate root id.")
    seen_ids.add(str(normalized["id"]))

    children = normalized.get("children") or []
    if len(children) > MAX_TOP_LEVEL_CHILDREN:
        raise ParentPathwayValidationError(
            f"Too many top-level steps ({len(children)}). "
            f"Keep at most {MAX_TOP_LEVEL_CHILDREN} — stay focused on what families should do first, "
            "not a full clinic protocol."
        )
    if len(children) > 5:
        warnings.append(
            f"Tree has {len(children)} top-level steps — keep the list short enough that overwhelmed "
            "families can act on it this month."
        )
    if normalized.get("about") is None:
        raise ParentPathwayValidationError(
            "Missing tree.about — required patient-facing intro: title plus summary in plain language."
        )

    for child in children:
        _walk_nodes(
            child,
            depth=1,
            seen_ids=seen_ids,
            node_count=node_count,
            allowed_pmids=allowed_pmids,
            warnings=warnings,
        )

    _validate_top_level_patient_chart_richness(normalized)

    return normalized, warnings


def validate_parent_pathway_json(
    raw_json: str,
    *,
    guideline_document: dict[str, Any] | None = None,
    extra_pmids: set[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Validate JSON string; optional guideline for PMID cross-check."""
    import json

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ParentPathwayValidationError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ParentPathwayValidationError("Pathway must be a JSON object.")
    data = coerce_pathway_tree_object(data)
    allowed: set[str] = set(extra_pmids or [])
    if guideline_document:
        allowed |= _collect_pmids_from_guideline(guideline_document)
    return validate_parent_pathway_tree(data, allowed_pmids=allowed if allowed else None)
