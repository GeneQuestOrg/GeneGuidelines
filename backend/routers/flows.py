"""
Flows API: list flows, full definition (nodes + edges), node updates.
DB calls run in run_in_executor so they do not block the event loop.
"""
import asyncio
import logging
import time
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from ..auth import require_api_key_if_set
from .. import database as db
from ..config import DB_PATH
from ..database import SQLITE_TIMEOUT
from ..agents.dynamic_output_schema import validate_output_schema_json
from ..agents.runner import _dbg
from ..models import (
    FlowDefinitionResponse,
    FlowNodeResponse,
    FlowNodeUpdate,
    FlowNodeUpdateBody,
    FlowNodeCreate,
    FlowEdgeResponse,
    FlowEdgeCreate,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/flows", tags=["flows"], dependencies=[Depends(require_api_key_if_set)])


def _run(f):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, f)


def _node_row_to_response(n):
    """Build FlowNodeResponse from DB row with safe types and defaults."""
    d = {k: v for k, v in dict(n).items() if isinstance(k, str)}
    # Required ints (SQLite can return other types)
    for key in ("max_retry", "version"):
        try:
            d[key] = int(d[key]) if d.get(key) is not None else (3 if key == "max_retry" else 1)
        except (TypeError, ValueError):
            d[key] = 3 if key == "max_retry" else 1
    # Required strings (never None for Pydantic / empty in UI)
    for key in ("flow_key", "node_id", "node_type", "label", "loop_policy", "execution_policy", "updated_at"):
        if d.get(key) is None:
            d[key] = "" if key != "label" else "(no label)"
    # prompt and description: always string (never null) so NodeEditor never has an empty field
    d["prompt"] = d.get("prompt") or ""
    d["description"] = d.get("description") or ""
    if d.get("prompt_mode") is None or str(d.get("prompt_mode") or "").strip() == "":
        d["prompt_mode"] = "agentic"
    d["model_name"] = d.get("model_name")
    d["output_schema_key"] = d.get("output_schema_key")
    d["output_schema"] = d.get("output_schema") or ""
    d["python_source"] = d.get("python_source") or ""
    d["http_url"] = d.get("http_url") or ""
    d["http_method"] = (d.get("http_method") or "GET").strip() or "GET"
    d["http_headers"] = d.get("http_headers") or ""
    d["http_body"] = d.get("http_body") or ""
    d["rag_operation"] = (d.get("rag_operation") or "similar").strip() or "similar"
    d["rag_body_json"] = d.get("rag_body_json") or ""
    d["merge_strategy"] = (d.get("merge_strategy") or "append").strip() or "append"
    d["merge_fields"] = d.get("merge_fields") or "[]"
    d["merge_key_field"] = d.get("merge_key_field") or "id"
    d["integration_operation"] = d.get("integration_operation") or ""
    d["integration_params_json"] = d.get("integration_params_json") or "{}"
    # Redact credentials — never return plaintext secrets to the client.
    # Non-empty string signals "credentials are set" without exposing them.
    raw_creds = d.get("integration_credentials_json") or ""
    d["integration_credentials_json"] = "***" if raw_creds.strip() else ""
    try:
        d["agentic_step_close"] = bool(int(d.get("agentic_step_close") or 0))
    except (TypeError, ValueError):
        d["agentic_step_close"] = str(d.get("agentic_step_close") or "").strip().lower() in ("1", "true", "yes")
    return FlowNodeResponse(**d)


def _edge_row_to_response(e):
    """Build FlowEdgeResponse from DB row with safe types."""
    d = {k: v for k, v in dict(e).items() if isinstance(k, str)}
    for key in ("flow_key", "source_node_id", "target_node_id"):
        if d.get(key) is None:
            d[key] = ""
    if d.get("label") is None:
        d["label"] = None
    return FlowEdgeResponse(**d)


def _get_flow_keys_safe():
    """Fetch flow_key. Force tuple rows (row_factory=None) so row[0] always works."""
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT)
    conn.row_factory = None
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL")
    cur.execute("SELECT DISTINCT flow_key FROM flow_definitions ORDER BY flow_key")
    rows = cur.fetchall()
    conn.close()
    return [str(r[0]) for r in rows]


def _row_to_dict(cur, row):
    """Row -> dict. row MUST be a tuple (conn.row_factory=None); otherwise row[i] on a dict raises KeyError."""
    if cur.description is None:
        return {}
    col_names = [cur.description[i][0] for i in range(len(cur.description))]
    if isinstance(row, (tuple, list)):
        return dict(zip(col_names, row))
    return {col_names[i]: row[col_names[i]] for i in range(len(col_names))}


def _get_nodes_and_edges_safe(flow_key: str):
    """Fetch nodes and edges (with position_x, position_y). row_factory=None -> always tuples."""
    db._ensure_position_columns()
    db._ensure_flow_execution_columns()
    db._ensure_output_schema_column()
    db._ensure_agentic_step_close_column()
    db._ensure_python_source_column()
    db._ensure_http_request_columns()
    db._ensure_rag_assist_columns()
    db._ensure_merge_columns()
    db._ensure_integration_columns()
    db._ensure_flow_edge_label_column()
    conn = sqlite3.connect(DB_PATH, timeout=SQLITE_TIMEOUT)
    conn.row_factory = None
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL")
    cur.execute(
        """SELECT flow_key, node_id, node_type, label, description, prompt, loop_policy, execution_policy,
                  max_retry, version, updated_at, position_x, position_y, prompt_mode, model_name, output_schema_key, output_schema, agentic_step_close, python_source,
                  http_url, http_method, http_headers, http_body, rag_operation, rag_body_json,
                  merge_strategy, merge_fields, merge_key_field, integration_operation, integration_params_json, integration_credentials_json
           FROM flow_definitions WHERE flow_key = ? ORDER BY id""",
        (flow_key,),
    )
    nodes = [_row_to_dict(cur, r) for r in cur.fetchall()]
    cur.execute(
        "SELECT flow_key, source_node_id, target_node_id, label FROM flow_edges WHERE flow_key = ? ORDER BY id",
        (flow_key,),
    )
    edges = [_row_to_dict(cur, r) for r in cur.fetchall()]
    conn.close()
    return nodes, edges


@router.get("/ping")
async def flows_ping():
    """Health check: confirms the flows router is loaded. Should return 200."""
    return {"ok": True, "router": "flows"}


@router.get("")
async def list_flows():
    """List flows. Returns raw dicts (no response_model)."""
    try:
        t0 = time.perf_counter()
        _dbg("H3", "list_flows: start", {"db_path": str(DB_PATH)}, run_id="flows_pre", location="backend/routers/flows.py:list_flows")
        db._ensure_position_columns()
        db._ensure_flow_execution_columns()
        db._ensure_output_schema_column()
        db._ensure_agentic_step_close_column()
        db._ensure_python_source_column()
        keys = _get_flow_keys_safe()
        _dbg("H3", "list_flows: keys loaded", {"flow_key_count": len(keys)}, run_id="flows_keys", location="backend/routers/flows.py:list_flows")
        out = []
        for flow_key in keys:
            nodes, edges = _get_nodes_and_edges_safe(flow_key)
            node_list = []
            for n in nodes:
                nd = dict(n)
                for key in ("max_retry", "version"):
                    try:
                        nd[key] = int(nd[key]) if nd.get(key) is not None else (3 if key == "max_retry" else 1)
                    except (TypeError, ValueError):
                        nd[key] = 3 if key == "max_retry" else 1
                for key in ("flow_key", "node_id", "node_type", "label", "loop_policy", "execution_policy", "updated_at"):
                    if nd.get(key) is None:
                        nd[key] = "" if key != "label" else "(no label)"
                nd["prompt"] = nd.get("prompt") or ""
                nd["description"] = nd.get("description") or ""
                if nd.get("prompt_mode") is None or str(nd.get("prompt_mode") or "").strip() == "":
                    nd["prompt_mode"] = "agentic"
                nd["output_schema"] = nd.get("output_schema") or ""
                nd["python_source"] = nd.get("python_source") or ""
                nd["http_url"] = nd.get("http_url") or ""
                nd["http_method"] = (nd.get("http_method") or "GET").strip() or "GET"
                nd["http_headers"] = nd.get("http_headers") or ""
                nd["http_body"] = nd.get("http_body") or ""
                nd["rag_operation"] = (nd.get("rag_operation") or "similar").strip() or "similar"
                nd["rag_body_json"] = nd.get("rag_body_json") or ""
                nd["integration_operation"] = nd.get("integration_operation") or ""
                nd["integration_params_json"] = nd.get("integration_params_json") or "{}"
                raw_creds_nd = nd.get("integration_credentials_json") or ""
                nd["integration_credentials_json"] = "***" if raw_creds_nd.strip() else ""
                try:
                    nd["agentic_step_close"] = bool(int(nd.get("agentic_step_close") or 0))
                except (TypeError, ValueError):
                    nd["agentic_step_close"] = str(nd.get("agentic_step_close") or "").strip().lower() in ("1", "true", "yes")
                node_list.append(nd)
            edge_list = []
            for edge in edges:
                ed = dict(edge)
                for key in ("flow_key", "source_node_id", "target_node_id"):
                    if ed.get(key) is None:
                        ed[key] = ""
                if ed.get("label") is None:
                    ed["label"] = None
                edge_list.append(ed)
            out.append({"flow_key": flow_key, "nodes": node_list, "edges": edge_list})
        dt_ms = int((time.perf_counter() - t0) * 1000)
        _dbg("H3", "list_flows: end", {"flow_count": len(out), "dt_ms": dt_ms}, run_id="flows_post", location="backend/routers/flows.py:list_flows")
        return out
    except HTTPException:
        raise
    except Exception as e:
        _dbg("H1", "list_flows: exception", {"error": str(e)}, run_id="flows_err", location="backend/routers/flows.py:list_flows")
        log.exception("list_flows failed")
        raise HTTPException(status_code=500, detail="Internal server error.") from e


@router.put("/node", response_model=FlowNodeResponse)
async def update_flow_node_body(body: FlowNodeUpdateBody):
    """Save node - single URL like Tools, with flow_key and node_id in the body."""
    try:
        flow_key = body.flow_key
        node_id = body.node_id
        node = await _run(lambda: db.get_flow_node(flow_key, node_id))
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        payload = body.model_dump(exclude_unset=True)
        payload.pop("flow_key", None)
        payload.pop("node_id", None)
        if not payload:
            return _node_row_to_response(node)
        if "output_schema" in payload and payload["output_schema"] is not None:
            os_raw = payload["output_schema"]
            if isinstance(os_raw, str) and os_raw.strip():
                try:
                    payload["output_schema"] = validate_output_schema_json(os_raw)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e)) from e
            elif os_raw == "":
                payload["output_schema"] = None
        updated = await _run(lambda: db.update_flow_node(flow_key, node_id, **payload))
        if not updated:
            raise HTTPException(status_code=404, detail="Node not found")
        return _node_row_to_response(updated)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Internal server error.",
        ) from e


@router.get("/{flow_key}", response_model=FlowDefinitionResponse)
async def get_flow(flow_key: str):
    """Full flow definition (nodes + edges)."""
    try:
        nodes = await _run(lambda: db.get_flow_definition_nodes(flow_key))
        if not nodes:
            raise HTTPException(status_code=404, detail="Flow not found")
        edges = await _run(lambda: db.get_flow_edges(flow_key))
        return FlowDefinitionResponse(
            flow_key=flow_key,
            nodes=[_node_row_to_response(n) for n in nodes],
            edges=[_edge_row_to_response(e) for e in edges],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Internal server error.",
        ) from e


@router.put("/{flow_key}/nodes/{node_id}", response_model=FlowNodeResponse)
async def update_flow_node(flow_key: str, node_id: str, body: FlowNodeUpdate):
    """Update node prompt/policies. Increments version."""
    try:
        node = await _run(lambda: db.get_flow_node(flow_key, node_id))
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")
        payload = body.model_dump(exclude_unset=True)
        if not payload:
            return _node_row_to_response(node)
        if "output_schema" in payload and payload["output_schema"] is not None:
            os_raw = payload["output_schema"]
            if isinstance(os_raw, str) and os_raw.strip():
                try:
                    payload["output_schema"] = validate_output_schema_json(os_raw)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e)) from e
            elif os_raw == "":
                payload["output_schema"] = None
        updated = await _run(lambda: db.update_flow_node(flow_key, node_id, **payload))
        if not updated:
            raise HTTPException(status_code=404, detail="Node not found")
        return _node_row_to_response(updated)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Internal server error.",
        ) from e


@router.post("/{flow_key}/nodes", response_model=FlowNodeResponse)
async def create_flow_node(flow_key: str, body: FlowNodeCreate):
    """Create a new node in the flow. node_id is generated (op-4, bl-10, …)."""
    try:
        payload = body.model_dump()
        created = await _run(
            lambda: db.create_flow_node(
                flow_key,
                node_type=payload.get("node_type", "action"),
                label=payload.get("label", "New node"),
                description=payload.get("description") or "",
                prompt=payload.get("prompt") or "",
                loop_policy=payload.get("loop_policy", "none"),
                execution_policy=payload.get("execution_policy", "auto"),
                max_retry=payload.get("max_retry", 3),
                python_source=payload.get("python_source"),
                http_url=payload.get("http_url"),
                http_method=payload.get("http_method"),
                http_headers=payload.get("http_headers"),
                http_body=payload.get("http_body"),
                rag_operation=payload.get("rag_operation"),
                rag_body_json=payload.get("rag_body_json"),
                merge_strategy=payload.get("merge_strategy"),
                merge_fields=payload.get("merge_fields"),
                merge_key_field=payload.get("merge_key_field"),
                integration_operation=payload.get("integration_operation"),
                integration_params_json=payload.get("integration_params_json"),
                integration_credentials_json=payload.get("integration_credentials_json"),
            )
        )
        if not created:
            raise HTTPException(status_code=500, detail="Failed to create node")
        return _node_row_to_response(created)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Internal server error.",
        ) from e


@router.delete("/{flow_key}/nodes/{node_id}")
async def delete_flow_node(flow_key: str, node_id: str):
    """Delete node and all its edges."""
    try:
        ok = await _run(lambda: db.delete_flow_node(flow_key, node_id))
        if not ok:
            raise HTTPException(status_code=404, detail="Node not found")
        return {"ok": True, "deleted": node_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Internal server error.",
        ) from e


@router.post("/{flow_key}/edges", response_model=FlowEdgeResponse)
async def create_flow_edge(flow_key: str, body: FlowEdgeCreate):
    """Create an edge between two nodes."""
    try:
        created = await _run(
            lambda: db.create_flow_edge(flow_key, body.source_node_id, body.target_node_id, body.label)
        )
        if not created:
            raise HTTPException(
                status_code=400,
                detail="Edge already exists or invalid (same source/target or missing nodes)",
            )
        return FlowEdgeResponse(**created)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Internal server error.",
        ) from e


@router.delete("/{flow_key}/edges")
async def delete_flow_edge(
    flow_key: str,
    source_node_id: str,
    target_node_id: str,
):
    """Delete one edge (query params: source_node_id, target_node_id)."""
    try:
        ok = await _run(lambda: db.delete_flow_edge(flow_key, source_node_id, target_node_id))
        if not ok:
            raise HTTPException(status_code=404, detail="Edge not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Internal server error.",
        ) from e
