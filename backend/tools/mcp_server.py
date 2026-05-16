"""
MCP server (Model Context Protocol) – tool set for AI agent.
Uses official mcp package (same as Pydantic AI client) for stdio compatibility.
Run: python mcp_server.py (from backend dir or: python -m backend.mcp_server from root)
"""
from __future__ import annotations

import json

from mcp.server import FastMCP

# When run as subprocess with cwd=backend, database and generated_tools are in the same directory
from backend import database as db
from backend.tools.generated.loader import load_generated_tools
from backend.tools.pubmed_runtime import register_pubmed_tools

# Schema + seed from JSON only when tables are empty
db.init_db()
db.run_seed_if_empty()

mcp = FastMCP(
    name="GeneGuidelines Clinical MCP",
    instructions=(
        "Clinical evidence and guideline tools for GeneGuidelines: PubMed search and fetch, "
        "parent pathway validation, and catalog introspection. Use PubMed tools for literature "
        "retrieval; do not invent PMIDs."
    ),
)

# Load generated tools (builder writes into backend/generated_tools)
_generated_tools_load_results = load_generated_tools(mcp)
register_pubmed_tools(mcp)
try:
    from backend.tools.parent_pathway_tools import register_parent_pathway_tools
except ImportError:
    from tools.parent_pathway_tools import register_parent_pathway_tools

register_parent_pathway_tools(mcp)


# --- List available MCP tools ---

@mcp.tool()
def list_available_tools() -> str:
    """
    Return list of all tools available on this MCP server.
    Call at the start to know which tools you can use for ticket diagnosis.
    """
    # Source of truth: tool_catalog in SQLite (seeded + builder additions).
    # This keeps UI catalog and agent-visible list consistent.
    rows = db.get_tool_catalog(enabled_only=True)
    lines = ["Available MCP tools:"]
    for r in rows:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        lines.append(f"- {name}")
    # Helpful debug: whether generated tools were loaded.
    if _generated_tools_load_results:
        ok = sum(1 for x in _generated_tools_load_results if x.get("status") == "registered")
        err = sum(1 for x in _generated_tools_load_results if str(x.get("status", "")).startswith("error:"))
        lines.append(f"(generated_tools loaded: registered={ok}, errors={err})")
    return "\n".join(lines) + "\n"


# --- Read-only tools (mock data) ---

@mcp.tool()
def ping_ip(ip: str) -> str:
    """Check host availability (ICMP ping). Returns mock network status."""
    if not ip or not ip.strip():
        return "Error: provide IP address."
    return f"Ping {ip.strip()}: 0% loss, 4 received, avg 2.3 ms. Host reachable."


@mcp.tool()
def get_server_logs(server_name: str) -> str:
    """Fetch latest server log entries. Returns mock errors/warnings."""
    if not server_name or not server_name.strip():
        return "Error: provide server name."
    name = server_name.strip()
    return (
        f"Server '{name}' logs (last 50 lines):\n"
        "- 10:01:22 WARN  [db] Pool connection timeout, retry in 5s\n"
        "- 10:01:27 INFO  [db] Connection restored\n"
        "- 10:02:01 ERROR [app] Request to /api/reports failed: 503 Service Unavailable\n"
        "- 10:02:15 WARN  [cache] Memory limit 80% reached\n"
    )


# --- AI Summary (agent calls at start; app reads from run_result) ---

@mcp.tool()
def set_ai_summary(issue: str, work_log_summary: str) -> str:
    """
    Set summary at start. Call at the BEGINNING of diagnosis, before other tools.
    issue: concrete problem in 1–2 sentences (what fails, where, for whom).
    work_log_summary: what the reporter already did and what is known from discussion – 2–4 sentences, so a human can understand context.
    """
    return "OK"

# --- Mutating tools (write to DB) ---

@mcp.tool()
def update_ticket_status(
    ticket_id: int,
    summary: str,
    status: str,
    steps_taken: list[str],
) -> str:
    """
    Update ticket record. Call at the END of diagnosis. Required.
    summary: Diagnosis in 2–5 sentences – what you checked (ping, logs), what they show, likely cause. Be specific so a technician can understand.
    status: in_progress or diagnosed. Use diagnosed when you have a conclusion and next steps.
    steps_taken: TECHNICIAN NEXT STEPS – list of concrete, actionable steps for the technician (e.g. "1. Restart service app-svc on 10.0.1.5", "2. Check /var/log/app/error.log for OOM", "3. Verify disk space on /data"). Never leave empty – always provide at least 2–3 steps the technician should perform. This is what the user sees as "next steps".
    """
    def _sanitize_summary_text(text: str) -> str:
        """Remove leaked system-instruction lines from user-facing diagnosis summary."""
        blocked_markers = (
            "important:",
            "critical rule",
            "request_missing_tool",
            "list_available_tools",
            "tool_catalog",
            "tool call",
            "mcp",
        )
        lines = [ln.rstrip() for ln in str(text or "").splitlines()]
        kept = [ln for ln in lines if ln.strip() and not any(m in ln.lower() for m in blocked_markers)]
        # Keep size reasonable for ticket UI while preserving diagnosis content.
        return "\n".join(kept).strip()[:1500]

    if status not in ("not_started", "in_progress", "diagnosed"):
        return f"Error: invalid status '{status}'. Allowed: not_started, in_progress, diagnosed."
    # Require concrete steps for the technician — reject empty input.
    if not steps_taken or not any(s and str(s).strip() for s in steps_taken):
        return (
            "Error: steps_taken is required and must contain at least 2–3 concrete steps for the technician. "
            "Example: ['1. Restart service X on server Y', '2. Check /var/log/app/error.log', '3. Verify disk space']. "
            "Call update_ticket_status again with a non-empty steps_taken list."
        )
    safe_summary = _sanitize_summary_text(summary)
    ok = db.update_ticket_status(ticket_id, safe_summary, status, steps_taken)
    if ok:
        return f"Ticket #{ticket_id} updated: status={status}, summary and steps saved."
    return f"Error: ticket with id={ticket_id} not found."


# --- Request missing tool ---

@mcp.tool()
def request_missing_tool(ticket_id: int, tool_name: str, reason: str) -> str:
    """
    Save a missing-tool request to tool_requests.
    Use when the agent needs access to an API/tool that is not available.
    """
    if not tool_name or not tool_name.strip():
        return "Error: provide tool name (tool_name)."
    name = tool_name.strip()
    canonical_name = db.canonicalize_tool_name(name)
    # #region request_missing_tool debug
    existing = []
    try:
        # Keep this check aligned with the acceptance rule used below.
        existing = [
            r
            for r in db.get_tool_catalog(enabled_only=False)
            if db.canonicalize_tool_name((r.get("name") or "").strip()) == canonical_name
        ]
    except Exception:
        existing = []
    # #endregion
    existing_catalog_ok = bool(existing)
    # Avoid duplicate requests when the tool already exists in the catalog.
    # (UI catalog is DB-backed, but agents can still mistakenly request tools that are present.)
    if existing:
        ret_obj = {
            "status": "skipped_exists_catalog",
            "tool_name": name,
            "canonical_name": canonical_name,
            "ticket_id": ticket_id,
            "reason": reason or "",
            "message": f"Tool '{name}' already exists in tool_catalog — not adding a missing-tool request.",
        }
        return json.dumps(ret_obj, ensure_ascii=False)

    try:
        reqs = db.get_tool_requests(ticket_id=ticket_id)
        existing_req = next(
            (
                r
                for r in reqs
                if db.canonicalize_tool_name((r.get("name") or "").strip()) == canonical_name
            ),
            None,
        )
    except Exception:
        existing_req = None

    if existing_req:
        status = (existing_req.get("status") or "requested").strip()
        ret_obj = {
            "status": "skipped_exists_request",
            "tool_name": name,
            "canonical_name": canonical_name,
            "ticket_id": ticket_id,
            "reason": reason or "",
            "existing_status": status,
            "message": (
                f"Missing-tool request '{name}' for ticket #{ticket_id} already exists "
                f"(existing status={status}) — skipping."
            ),
        }
        return json.dumps(ret_obj, ensure_ascii=False)

    db.add_missing_tool_request(ticket_id, name, reason or "No reason given.")
    ret_obj = {
        "status": "created",
        "tool_name": name,
        "canonical_name": canonical_name,
        "ticket_id": ticket_id,
        "reason": reason or "",
        "message": f"Missing-tool request '{name}' for ticket #{ticket_id} saved to backlog.",
    }
    return json.dumps(ret_obj, ensure_ascii=False)


# --- Dangerous tool (requires human approval on client) ---

@mcp.tool()
def restart_service(service_name: str, server_ip: str) -> str:
    """
    Restart service on remote server.
    WARNING: Human authorization required on the client before calling.
    """
    if not service_name or not server_ip:
        return "Error: provide service_name and server_ip."
    return (
        f"Action requiring authorization: restart service '{service_name.strip()}' on {server_ip.strip()}. "
        "Not executed – human approval required in the app."
    )


if __name__ == "__main__":
    mcp.run()
