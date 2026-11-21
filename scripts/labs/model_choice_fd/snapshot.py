"""Freeze every input once, with the product's own code, so every arm reads byte-identical prompts.

What is frozen, and how:

- **Synthesis.** The FD source shelf comes from the public API (``/api/diseases/fd/source-documents``); the product's own ``GuidelineShelfLoadExecutor`` then fetches abstracts and open-access full text from NCBI exactly as a run does, with the shelf budget production uses for sections on a direct (frontier) model. The five ``gs-sec-*`` prompts are rendered with the engine's own helpers (``build_node_prompt``, ``_interpolate_node_prompt``, ``build_simple_llm_prompts``) from the bundled spec, which production syncs into ``flow_definitions`` on every start. The stored production synthesis is saved as the shipped baseline.
- **PubMed draft.** The pubmed flow is defined in code (``backend/database.py``, ``_ensure_pubmed_flow``); its node rows are captured by running that function against a recording stand-in for the database connection, so the prompts, schemas and retry counts are exactly what it would write. ``pm-1`` (deterministic PubMed retrieval), ``pm-rag`` and the ``pm-2`` code node then run for real, and the ``pass1-diagnostics`` and ``pm-4-diagnostics`` prompts are rendered with the engine's helpers.
- **Search.** The 30 known-answer queries in ``cases/search_queries.jsonl`` are copied with their hash; the product builds its prompts from the query at run time, deterministically.
- **Doctors.** The public FD directory is saved for the record of task 3 (see README: there is no model call in that path).

Nothing here writes to any database: ``env.load_product_env`` points ``DB_URL`` at an address nothing listens on.
"""

from __future__ import annotations

import asyncio
import json
import urllib.request
from pathlib import Path
from typing import Any

from .common import (
    CASES_DIR,
    REPO_ROOT,
    SNAPSHOT_DIR,
    LabError,
    git_state,
    now_iso,
    read_json,
    read_jsonl,
    sha256_file,
    source_hashes,
    write_json,
)

API_BASE = "https://geneguidelines.genequest.org/api"
SLUG = "fd"
TICKET_ID = 0  # production uses the id of the ticket it creates; one fixed value keeps prompts identical across arms
PUBMED_UNITS = ("pass1-diagnostics", "pm-4-diagnostics")
_FORBIDDEN_PLACEHOLDERS = ("{{ticket_summary}}", "{{tools_list}}", "{{previous_output}}")


def _get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "geneguidelines-model-experiment", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def snapshot_path(name: str) -> Path:
    return SNAPSHOT_DIR / name


def load_snapshot(name: str, task: str) -> dict:
    path = snapshot_path(name) / f"{task}.json"
    if not path.is_file():
        raise LabError(f"No {task} snapshot at {path}; run `lab.py snapshot --name {name}` first")
    return read_json(path)


def snapshot_hash(name: str, task: str) -> str:
    return sha256_file(snapshot_path(name) / f"{task}.json")


def _render_simple_prompt(node: dict, store: dict, *, flow_key: str, title: str, description: str) -> tuple[str, str]:
    """The (system, user) pair the fork engine sends for a prompt_mode=simple node (flow_engine._execute_node_wave)."""
    from backend.engine.flow_engine import (
        _SIMPLE_NODE_SYSTEM_PROMPT_HEAD,
        _interpolate_node_prompt,
        get_previous_output_summary,
    )
    from backend.engine.prompt_formatting import build_node_prompt, build_simple_llm_prompts

    raw = (node.get("prompt") or "").strip()
    for placeholder in _FORBIDDEN_PLACEHOLDERS:
        if placeholder in raw:
            raise LabError(f"{node.get('node_id')}: prompt uses {placeholder}, which needs the tool catalog or ticket state this lab does not reproduce")
    ticket_summary = f"Ticket #{TICKET_ID}. Title: {title}. Description: {description}."
    prompt = build_node_prompt(raw, ticket_summary, "(not used by this node)", get_previous_output_summary(store))
    prompt = _interpolate_node_prompt(prompt, store, flow_key=flow_key, node_id=str(node["node_id"]))
    return build_simple_llm_prompts(prompt, system_head=_SIMPLE_NODE_SYSTEM_PROMPT_HEAD, ticket_id=TICKET_ID, title=title, description=description, comments_text="")


# --- synthesis -----------------------------------------------------------------------------------------------------------

async def build_synthesis() -> dict:
    from backend.agents.simple_runner import resolve_max_tokens_for_node
    from backend.contracts.guidelines_v1 import SYNTHESIS_SECTIONS
    from backend.executors.base import NodeInput
    from backend.executors.guidelines import guideline_shelf_load_executor as shelf_mod
    from backend.guidelines.models import SourceDocument

    disease = _get_json(f"{API_BASE}/diseases/{SLUG}")
    raw_docs = _get_json(f"{API_BASE}/diseases/{SLUG}/source-documents")
    shipped = _get_json(f"{API_BASE}/diseases/{SLUG}/guideline-synthesis")
    docs = [
        SourceDocument(disease_slug=SLUG, doc_id=str(d["id"]), role=d["role"], title=d["title"], authors=d["authors"], journal=d["journal"], year=str(d["year"]), scope=d["scope"], covers=list(d.get("covers") or []), pmid=d.get("pmid"), bookshelf=d.get("bookshelf"), pmcid=d.get("pmcid"), free_full_text=bool(d.get("freeFullText")), is_new=bool(d.get("isNew")), updates_note=d.get("updatesNote"))
        for d in raw_docs
    ]

    class _ApiShelf:
        def list_source_documents(self, slug: str):
            return list(docs)

    # Production runs every gs-sec node on the direct frontier path (spec + startup sync), so the shelf gets that budget. The original reads flow_definitions; this lab has no database.
    shelf_mod._sections_run_on_a_direct_model = lambda: True
    shelf_out = await shelf_mod.GuidelineShelfLoadExecutor(repo=_ApiShelf()).execute(NodeInput(node_config={"node_id": "gs-shelf", "node_type": "guideline_shelf_load"}, context={}, initial_data={"disease_slug": SLUG}))
    shelf = shelf_out.data
    if not shelf.get("ok"):
        raise LabError(f"Shelf load failed: {shelf.get('error')}")

    spec = read_json(REPO_ROOT / "backend/flows/specs/guideline_synthesis.json")
    name = str(disease["name"]).strip()
    title = f"Synthesis · {name}"
    description = f"Guideline synthesis (level a) over the source shelf for {name}."
    initial = {"disease_slug": SLUG, "disease_name": name, "sections": [dict(s) for s in SYNTHESIS_SECTIONS]}
    store = {"node_outputs": {"gs-shelf": shelf}, "initial_context": initial}
    units = []
    for node in spec["nodes"]:
        if not str(node.get("node_id", "")).startswith("gs-sec-"):
            continue
        system, user = _render_simple_prompt(node, store, flow_key="guideline_synthesis", title=title, description=description)
        units.append({
            "unit": node["node_id"],
            "section_id": node["node_id"].removeprefix("gs-sec-"),
            "system": system,
            "user": user,
            "schema_key": node.get("output_schema_key"),
            "shipped_model_name": node.get("model_name"),
            "product_max_tokens": resolve_max_tokens_for_node({**node, "prompt_mode": "simple"}),
            "max_retry": int(node.get("max_retry") or 3),
        })
    return {
        "task": "synthesis",
        "disease": disease,
        "initial": initial,
        "shelf_docs": shelf["shelf_docs"],
        "shelf_pmids": shelf.get("shelf_pmids") or [],
        "fulltexts_fetched": shelf.get("fulltexts_fetched"),
        "abstracts_fetched": shelf.get("abstracts_fetched"),
        "units": units,
        "shipped": shipped,
    }


# --- pubmed --------------------------------------------------------------------------------------------------------------

class _RecordingCursor:
    """Stands in for the database while _ensure_pubmed_flow runs: every SELECT finds nothing, every write is recorded."""

    def __init__(self, sink: list) -> None:
        self.sink = sink
        self._last = None

    def execute(self, sql: str, params: Any = None) -> None:
        text = " ".join(sql.split())
        self.sink.append((text, params))
        self._last = {"n": 0} if "COUNT(*)" in text else ({"id": 1} if "RETURNING" in text else None)

    def fetchone(self):
        return self._last

    def fetchall(self):
        return []


class _RecordingConnection:
    def __init__(self, sink: list) -> None:
        self.sink = sink

    def cursor(self):
        return _RecordingCursor(self.sink)

    def commit(self):
        return None

    def close(self):
        return None


def code_defined_pubmed_nodes() -> dict[str, dict]:
    """The pubmed node rows exactly as _ensure_pubmed_flow would INSERT them into flow_definitions."""
    from backend import database

    sink: list = []
    original_conn, original_col = database.get_connection, database._ensure_evaluation_source_nodes_column
    database.get_connection = lambda *a, **k: _RecordingConnection(sink)
    database._ensure_evaluation_source_nodes_column = lambda: None
    try:
        database._ensure_pubmed_flow()
    finally:
        database.get_connection, database._ensure_evaluation_source_nodes_column = original_conn, original_col
    columns = ("flow_key", "node_id", "node_type", "label", "description", "prompt", "max_retry", "version", "updated_at", "position_x", "position_y", "prompt_mode", "model_name", "output_schema_key", "output_schema", "agentic_step_close", "python_source")
    nodes = {}
    for sql, params in sink:
        if sql.startswith("INSERT INTO flow_definitions"):
            row = dict(zip(columns, params))
            nodes[row["node_id"]] = row
    if not nodes:
        raise LabError("Capturing the code-defined pubmed flow produced no rows; backend/database.py changed shape")
    return nodes


async def build_pubmed() -> dict:
    from backend.agents.simple_runner import resolve_max_tokens_for_node
    from backend.executors.base import NodeInput
    from backend.executors.code_node_runner import run_code_node_async
    from backend.executors.guidelines.guidelines_rag_executor import GuidelinesRagExecutor
    from backend.flows.pubmed.prompt_context import pm2_view_for_llm_prompt
    from backend.flows.pubmed.retrieval import run_pm1_retrieval
    from backend.guideline_prompt_profile import build_disease_flow_initial_fields
    from backend.routers.pipeline import _guideline_ticket_description

    disease = _get_json(f"{API_BASE}/diseases/{SLUG}")
    seed = read_json(REPO_ROOT / "backend/content_seed.json")
    seed_row = next((d for d in seed.get("diseases", []) if d.get("slug") == SLUG), {})
    disease_row = {**disease, "guidelinePromptProfile": seed_row.get("guidelinePromptProfile")}
    initial = build_disease_flow_initial_fields(disease_row)
    title = str(disease["name"]).strip()
    description = _guideline_ticket_description(disease_row)
    nodes = code_defined_pubmed_nodes()

    ticket = {"id": TICKET_ID, "title": title, "description": description, "comments_text": ""}
    pm1 = await asyncio.to_thread(run_pm1_retrieval, {"ticket": ticket, "initial": initial, "outputs": {}})
    pm1_out = {"result": pm1, "output_text": json.dumps(pm1, ensure_ascii=False), "ai_summary": {}}
    rag = await GuidelinesRagExecutor().execute(NodeInput(node_config=nodes["pm-rag"], context={}, initial_data=initial))
    outputs: dict[str, Any] = {"pm-1": pm1_out, "pm-rag": rag.data}
    pm2 = await run_code_node_async(python_source=nodes["pm-2"]["python_source"], context={"ticket": ticket, "initial": initial, "outputs": outputs}, node_id="pm-2")
    if not pm2.get("ok"):
        raise LabError(f"pm-2 code node failed: {pm2.get('error')}")
    outputs["pm-2"] = pm2
    # The drafting node reads the evidence pass by name. Its rendered prompt does not depend on what the evidence pass wrote (see README, finding on interpolation), which this placeholder makes checkable.
    outputs["pass1-diagnostics"] = {"key_findings": "(evidence-pass output)"}
    store = {"node_outputs": outputs, "initial_context": initial}
    units = []
    for unit in PUBMED_UNITS:
        node = nodes[unit]
        system, user = _render_simple_prompt(node, store, flow_key="pubmed", title=title, description=description)
        units.append({
            "unit": unit,
            "system": system,
            "user": user,
            "output_schema": node.get("output_schema"),
            "product_max_tokens": resolve_max_tokens_for_node({**node, "prompt_mode": "simple"}),
            "max_retry": int(node.get("max_retry") or 3),
            "evidence_pass_reaches_prompt": "(evidence-pass output)" in user,
            "consensus_context_reaches_prompt": bool((rag.data.get("consensus_context") or "")[:200]) and (rag.data.get("consensus_context") or "")[:200] in user,
        })
    view = pm2_view_for_llm_prompt("pass1-diagnostics", pm2)
    view_result = view.get("result", view) if isinstance(view, dict) else {}
    articles = pm1.get("articles") or []
    return {
        "task": "pubmed",
        "disease": disease_row,
        "initial": initial,
        "node_definitions": {k: {f: v for f, v in nodes[k].items() if f != "python_source"} for k in ("pm-rag", *PUBMED_UNITS)},
        "corpus": [{"pmid": str(a.get("pmid")), "title": a.get("title"), "abstract": a.get("abstract"), "pubdate": a.get("pubdate")} for a in articles],
        "corpus_pmids": sorted({str(a.get("pmid")) for a in articles if a.get("pmid")}),
        "prompt_article_count": view_result.get("article_count"),
        "consensus_context_chars": len(rag.data.get("consensus_context") or ""),
        "units": units,
    }


# --- search, doctors, manifest -------------------------------------------------------------------------------------------

def build_search() -> dict:
    path = CASES_DIR / "search_queries.jsonl"
    return {"task": "search", "cases": read_jsonl(path), "cases_sha256": sha256_file(path)}


def build_doctors() -> dict:
    return {"task": "doctors", "directory": _get_json(f"{API_BASE}/diseases/{SLUG}/doctors")}


async def build_snapshot(name: str, only: tuple[str, ...]) -> Path:
    folder = snapshot_path(name)
    for task in only:
        if (folder / f"{task}.json").exists():
            raise LabError(f"{folder}/{task}.json exists; snapshots are frozen. Choose a new --name.")
    folder.mkdir(parents=True, exist_ok=True)
    builders = {"synthesis": build_synthesis, "pubmed": build_pubmed}
    for task in only:
        if task in builders:
            data = await builders[task]()
        elif task == "search":
            data = build_search()
        elif task == "doctors":
            data = build_doctors()
        else:
            raise LabError(f"Unknown snapshot part {task}")
        write_json(folder / f"{task}.json", data)
        print(f"  {task}: {folder / f'{task}.json'} ({(folder / f'{task}.json').stat().st_size:,} bytes)")
    commit, dirty = git_state()
    manifest_path = folder / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else {"name": name, "parts": {}}
    for task in only:
        manifest["parts"][task] = {"sha256": sha256_file(folder / f"{task}.json"), "created_at": now_iso(), "git_commit": commit, "git_dirty": dirty, "api_base": API_BASE}
    manifest["product_sources"] = source_hashes()
    write_json(manifest_path, manifest)
    return folder
