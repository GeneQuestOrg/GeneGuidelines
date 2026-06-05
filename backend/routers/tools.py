"""
Tools API: MCP catalog, requested queue, implemented entries.
DB calls run in run_in_executor so they do not block the event loop.
Reserve for Builder: invokes the builder flow (run_developer_flow) and returns its steps (builder "thoughts").
"""
import asyncio
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import require_api_key_if_set
from .. import database as db
from ..tools.agent_tools import run_developer_flow
from ..models import (
    ToolCatalogItem,
    ToolCatalogUpdate,
    ToolRequestCreate,
    ToolRequestResponse,
    ToolImplementationResponse,
)

router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(require_api_key_if_set)])


def _run(f):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, f)


@router.get("/catalog", response_model=list[ToolCatalogItem])
async def get_tool_catalog(enabled_only: bool = True):
    """MCP tool catalog."""
    rows = await _run(lambda: db.get_tool_catalog(enabled_only=enabled_only))
    return [ToolCatalogItem(**r) for r in rows]


@router.put("/catalog/{id}", response_model=ToolCatalogItem)
async def update_tool_catalog(id: int, body: ToolCatalogUpdate):
    """Update execution_mode (auto | approval) for a catalog entry."""
    row = await _run(lambda: db.get_tool_catalog_by_id(id))
    if not row:
        raise HTTPException(status_code=404, detail="Catalog entry not found")
    if body.execution_mode not in ("auto", "approval"):
        raise HTTPException(status_code=400, detail="execution_mode: only 'auto' or 'approval'")
    ok = await _run(lambda: db.update_tool_catalog_execution_mode(id, body.execution_mode))
    if not ok:
        raise HTTPException(status_code=404, detail="Catalog entry not found")
    row = await _run(lambda: db.get_tool_catalog_by_id(id))
    return ToolCatalogItem(**row)


@router.get("/requested", response_model=list[ToolRequestResponse])
async def get_requested_queue(ticket_id: int | None = Query(None, description="Optional filter by ticket_id")):
    """Queue of requested tools."""
    rows = await _run(lambda: db.get_tool_requests(ticket_id=ticket_id))
    return [ToolRequestResponse(**r) for r in rows]


@router.post("/requested", response_model=ToolRequestResponse, status_code=201)
async def add_tool_request(body: ToolRequestCreate):
    """Add a new tool request."""
    new_id = await _run(lambda: db.add_tool_request(
        name=body.name,
        note=body.note,
        ticket_id=body.ticket_id,
        status=body.status,
    ))
    row = await _run(lambda: db.get_tool_request_by_id(new_id))
    return ToolRequestResponse(**row)


@router.get("/implemented", response_model=list[ToolImplementationResponse])
async def get_implemented():
    """List of implemented tools (tool_implementations – PR/merged)."""
    rows = await _run(db.get_tool_implementations)
    return [ToolImplementationResponse(**r) for r in rows]


@router.post("/requested/{request_id}/reserve")
async def reserve_for_builder(request_id: int, body: dict | None = None):
    """
    Reserve a request for the builder and run the flow (implementation, branch, PR, registration).
    Returns ok, reason?, request_id, steps (list of { step, msg, ... } - builder "thoughts"), pr_url?, duplicate_of?.
    """
    builder_agent_id = (body or {}).get("builder_agent_id") or f"governance-{uuid4().hex[:8]}"
    req = await _run(lambda: db.get_tool_request_by_id(request_id))
    if not req:
        raise HTTPException(status_code=404, detail="Tool request not found")
    result = await _run(
        lambda: run_developer_flow(request_id, builder_agent_id)
    )
    # Ensure "implemented" registry is updated immediately after reserve flow,
    # even when no PR is created (ready_for_pr).
    await _run(db.get_tool_implementations)
    # Always return 200 + JSON (even on ok: false) so the frontend can render steps and reason
    return {
        "ok": result.get("ok", False),
        "reason": result.get("reason"),
        "request_id": result.get("request_id", request_id),
        "steps": result.get("steps", []),
        "pr_url": result.get("pr_url"),
        "duplicate_of": result.get("duplicate_of"),
    }
