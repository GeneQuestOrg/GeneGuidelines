"""
Tickets CRUD – FastAPI. Paths per tutorial: /api/tickets, /api/tickets/{id}, ...
DB calls run in thread pool so they don't block the event loop (avoids infinite loading / timeouts).
"""
import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException

from ..account.deps import require_superadmin
from .. import database as db
from ..agents.runner import _dbg
from ..models import (
    TicketCreate,
    TicketUpdate,
    TicketResponse,
    CommentCreate,
    CommentResponse,
    MissingToolRequestResponse,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])


def _run(f):
    """Run sync DB call in thread pool."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, f)


@router.get("", response_model=list[TicketResponse])
async def list_tickets():
    """List all tickets. On error return [] so the UI does not hang."""
    try:
        t0 = asyncio.get_running_loop().time()
        _dbg("H1", "list_tickets: start", {"db_path": str(getattr(db, "DB_PATH", ""))}, run_id="tickets_pre", location="backend/routers/tickets.py:list_tickets")
        def _call():
            t1 = time.perf_counter()
            rows_local = db.get_all_tickets()
            t2 = time.perf_counter()
            # Note: executor function, so time is approximate; still useful for "blocked vs fast".
            _dbg("H1", "list_tickets: db call finished", {"dt_ms": int((t2 - t1) * 1000)}, run_id="tickets_db", location="backend/routers/tickets.py:list_tickets")
            return rows_local
        rows = await _run(_call)
        dt_ms = int((asyncio.get_running_loop().time() - t0) * 1000)
        _dbg("H1", "list_tickets: end", {"count": len(rows), "dt_ms": dt_ms}, run_id="tickets_post", location="backend/routers/tickets.py:list_tickets")
        return [TicketResponse(**r) for r in rows]
    except Exception as ex:
        _dbg("H2", "list_tickets: exception", {"error": str(ex)}, run_id="tickets_err", location="backend/routers/tickets.py:list_tickets")
        return []


@router.post("/admin/reset-statuses", dependencies=[Depends(require_superadmin)])
async def reset_all_ticket_statuses():
    """Reset all tickets to not_started and clear summaries/diagnostic steps."""
    n = await _run(db.reset_all_tickets_to_not_started)
    return {"ok": True, "reset": n, "status": "not_started"}


@router.get("/{id}", response_model=TicketResponse)
async def get_ticket(id: int):
    """Get one ticket by id."""
    _dbg("H13", "get_ticket called", {"id": id}, run_id="post-sse", location="backend/routers/tickets.py:get_ticket")
    t = await _run(lambda: db.get_ticket_by_id(id))
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    resp = TicketResponse(**t)
    _dbg(
        "H13b",
        "get_ticket returning",
        {"id": id, "status": resp.status, "has_resolution": bool(resp.resolution_summary)},
        run_id="post-sse",
        location="backend/routers/tickets.py:get_ticket:return",
    )
    return resp


@router.post("", response_model=TicketResponse, status_code=201)
async def create_ticket(body: TicketCreate):
    """Create a new ticket."""
    new_id = await _run(lambda: db.create_ticket(
        title=body.title,
        description=body.description or "(no description)",
        reporter_name=body.reporter_name,
        category=body.category,
    ))
    t = await _run(lambda: db.get_ticket_by_id(new_id))
    return TicketResponse(**t)


@router.put("/{id}", response_model=TicketResponse)
async def update_ticket(id: int, body: TicketUpdate):
    """Update ticket (status, summary, other fields optional)."""
    t = await _run(lambda: db.get_ticket_by_id(id))
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        return TicketResponse(**t)
    ok = await _run(lambda: db.update_ticket(id, **payload))
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid data (e.g. status)")
    t = await _run(lambda: db.get_ticket_by_id(id))
    return TicketResponse(**t)


@router.delete("/{id}", status_code=204)
async def delete_ticket(id: int):
    """Delete ticket."""
    ok = await _run(lambda: db.delete_ticket(id))
    if not ok:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return None


@router.get("/{id}/comments", response_model=list[CommentResponse])
async def list_comments(id: int):
    """List comments for ticket."""
    t = await _run(lambda: db.get_ticket_by_id(id))
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    rows = await _run(lambda: db.get_comments_for_ticket(id))
    return [CommentResponse(**r) for r in rows]


@router.post("/{id}/comments", response_model=CommentResponse, status_code=201)
async def add_comment(id: int, body: CommentCreate):
    """Add a comment to ticket."""
    t = await _run(lambda: db.get_ticket_by_id(id))
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    await _run(lambda: db.add_comment(id, body.author, body.content))
    rows = await _run(lambda: db.get_comments_for_ticket(id))
    last = rows[-1] if rows else {"id": 0, "ticket_id": id, "author": body.author, "content": body.content, "created_at": ""}
    return CommentResponse(**last)


@router.get("/{id}/missing-tools", response_model=list[MissingToolRequestResponse])
async def list_missing_tool_requests(id: int):
    """Missing tool requests for ticket (tool_requests)."""
    t = await _run(lambda: db.get_ticket_by_id(id))
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    rows = await _run(lambda: db.get_missing_tool_requests(id))
    return [MissingToolRequestResponse(**r) for r in rows]
