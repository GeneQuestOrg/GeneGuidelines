"""Derive public progress hints for in-flight research runs."""
from __future__ import annotations

from dataclasses import dataclass

try:
    from ..database import get_flow_definition_nodes, get_flow_node
except ImportError:
    from database import get_flow_definition_nodes, get_flow_node  # type: ignore[no-redef]


@dataclass(frozen=True, slots=True)
class RunProgress:
    """Lightweight progress snapshot safe for the public API."""

    progress_pct: int
    activity: str


# (elapsed_sec threshold, user-facing message) — used when no live agent store exists.
_PIPELINE_TIMELINE: dict[str, list[tuple[int, str]]] = {
    "official_guidelines_finder": [
        (0, "Searching PubMed for consensus papers…"),
        (60, "Ranking candidate guideline sources…"),
        (120, "Validating publication metadata…"),
    ],
    "trials_finder": [
        (0, "Querying ClinicalTrials.gov…"),
        (45, "Matching trials to this disease…"),
        (90, "Extracting structured trial fields…"),
    ],
    "therapies_finder": [
        (0, "Searching PubMed for therapy reviews…"),
        (60, "Filtering high-signal publications…"),
        (120, "Extracting therapy recommendations…"),
    ],
    "foundations_finder": [
        (0, "Identifying patient advocacy foundations…"),
        (45, "Verifying organization websites…"),
        (90, "Saving foundation contacts…"),
    ],
    "doctor_finder": [
        (0, "Collecting PubMed author records…"),
        (120, "Resolving affiliations and locations…"),
        (300, "Building the specialist directory…"),
        (600, "Enriching remaining affiliations…"),
    ],
    "bootstrap": [
        (0, "Starting parallel research workflows…"),
        (30, "Official guidelines and trials in progress…"),
        (90, "Guideline pipeline and doctor finder running…"),
    ],
}

_PIPELINE_EXPECTED_SEC: dict[str, int] = {
    "official_guidelines_finder": 180,
    "trials_finder": 180,
    "therapies_finder": 180,
    "foundations_finder": 180,
    "doctor_finder": 900,
    "bootstrap": 120,
    "guideline": 2400,
    "parent_pathway": 600,
    "pubmed": 2400,
}


def _humanize_node_id(flow_key: str, node_id: str) -> str:
    node = get_flow_node(flow_key, node_id)
    if node is not None:
        label = str(node.get("label") or "").strip()
        if label:
            return label
    readable = node_id.replace("-", " ").replace("_", " ")
    if readable.startswith("pm "):
        readable = readable.replace("pm ", "PubMed ", 1)
    return readable[:1].upper() + readable[1:] if readable else "Processing"


def _activity_from_agent_store(run: dict[str, object], flow_key: str) -> str:
    ai = run.get("ai_summary")
    if isinstance(ai, dict):
        work_log = str(ai.get("work_log_summary") or "").strip()
        if work_log:
            return work_log[:160]
        issue = str(ai.get("issue") or "").strip()
        if issue:
            return issue[:160]

    node_outputs = run.get("node_outputs")
    if isinstance(node_outputs, dict) and node_outputs:
        last_node_id = list(node_outputs.keys())[-1]
        if isinstance(last_node_id, str) and last_node_id:
            return f"Running step: {_humanize_node_id(flow_key, last_node_id)}"

    diagnostics = run.get("diagnostics_entries")
    if isinstance(diagnostics, list):
        for entry in reversed(diagnostics):
            if not isinstance(entry, dict):
                continue
            tool = str(entry.get("tool") or "").strip()
            result = str(entry.get("result") or "").strip()
            if tool and result and result.upper() != "OK":
                return f"{tool}: {result}"[:160]
            if tool:
                return f"Using {tool}…"[:160]

    return _default_flow_activity(flow_key)


def _progress_from_agent_store(run: dict[str, object], flow_key: str) -> int:
    node_outputs = run.get("node_outputs")
    completed = len(node_outputs) if isinstance(node_outputs, dict) else 0
    nodes = get_flow_definition_nodes(flow_key) or []
    executable = [
        n
        for n in nodes
        if str(n.get("node_type") or "") not in ("merge", "decision")
    ]
    total = max(len(executable), len(nodes), 1)
    if bool(run.get("done")):
        return 100
    if completed <= 0:
        return 8
    return min(99, max(8, int(completed / total * 100)))


def _timeline_activity(pipeline: str, elapsed_sec: int | None) -> str:
    elapsed = max(0, elapsed_sec or 0)
    timeline = _PIPELINE_TIMELINE.get(pipeline) or _PIPELINE_TIMELINE.get("bootstrap", [])
    activity = timeline[0][1] if timeline else "Research in progress…"
    for threshold, message in timeline:
        if elapsed >= threshold:
            activity = message
    return activity


def _timeline_progress(pipeline: str, flow_key: str, elapsed_sec: int | None) -> int:
    elapsed = max(0, elapsed_sec or 0)
    expected = _PIPELINE_EXPECTED_SEC.get(pipeline) or _PIPELINE_EXPECTED_SEC.get(
        flow_key, 300
    )
    return min(92, max(5, int(elapsed / expected * 100)))


def _default_flow_activity(flow_key: str) -> str:
    key = flow_key.strip().lower()
    if key == "pubmed":
        return "Building evidence-backed guideline sections…"
    if key == "parent_pathway":
        return "Generating care pathway diagram…"
    if key == "doctor_finder":
        return "Building specialist directory…"
    return "Running research workflow…"


def _load_agent_run(run_id: str) -> dict[str, object] | None:
    try:
        from ..routers.agent import AGENT_RUNS, _AGENT_STORAGE_LOCK
    except ImportError:
        return None
    with _AGENT_STORAGE_LOCK:
        run = AGENT_RUNS.get(run_id)
    if run is None:
        return None
    return dict(run)


def resolve_run_progress(
    *,
    run_id: str,
    flow_key: str,
    pipeline: str,
    elapsed_sec: int | None,
) -> RunProgress:
    """Best-effort progress for an active run (never raises)."""
    flow = (flow_key or pipeline or "guideline").strip().lower()
    pipe = (pipeline or flow).strip().lower()

    agent_run = _load_agent_run(run_id)
    if agent_run is not None and not bool(agent_run.get("done")):
        return RunProgress(
            progress_pct=_progress_from_agent_store(agent_run, flow),
            activity=_activity_from_agent_store(agent_run, flow),
        )

    return RunProgress(
        progress_pct=_timeline_progress(pipe, flow, elapsed_sec),
        activity=_timeline_activity(pipe, elapsed_sec),
    )


__all__ = ["RunProgress", "resolve_run_progress"]
