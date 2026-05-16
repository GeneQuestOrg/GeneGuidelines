"""Agent runner (Pydantic AI + MCP).

Trace events are pushed onto a thread-safe queue and streamed by
``GET /api/agent/trace/{execution_id}`` over SSE.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import traceback
from pathlib import Path
from queue import Queue
from typing import Any

from dotenv import load_dotenv

# Load .env from the project root regardless of cwd.
_load_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_load_env_path)
from .. import database as db
from ..config import AGENT_PYDANTIC_AI_REQUEST_LIMIT, AGENT_RUN_TIMEOUT_SEC

from . import agent as agent_module

# Pydantic AI imports at module load (in the runner thread, not in the agent thread):
# importing in a fresh thread can deadlock on Windows.
from pydantic_ai.agent import CallToolsNode, ModelRequestNode
from pydantic_ai.usage import UsageLimits
from pydantic_ai.messages import (
    BuiltinToolCallPart,
    ToolCallPart,
    ToolReturnPart,
    BuiltinToolReturnPart,
    TextPart,
)

# pydantic_ai defaults request_limit=50; MCP-heavy flows (e.g. patient chart) exceed it quickly.
_AGENT_USAGE_LIMITS = UsageLimits(request_limit=AGENT_PYDANTIC_AI_REQUEST_LIMIT)


def _looks_polish(text: str) -> bool:
    s = (text or "").lower()
    if not s:
        return False
    return any(ch in s for ch in "ąćęłńóśźż") or any(tok in s for tok in (" prośb", " zgłosz", " usunię", " grupa ", "technik"))


def _shorten_mcp_content(content: Any, max_len: int = 60) -> str:
    if content is None:
        return "ok"
    s = content if isinstance(content, str) else str(content)
    s = s.strip().split("\n")[0] if s else ""
    s = s.strip() or "ok"
    if len(s) <= max_len:
        return s
    cut = s[: max_len + 1]
    last_space = cut.rfind(" ")
    if last_space > max_len // 2:
        return cut[:last_space].strip() + "…"
    return cut[:max_len].strip() + "…"


def _traceback_indicates_mcp_init_failure(tb: str) -> bool:
    """True when MCP stdio client failed during init (e.g. McpError / Connection closed / TaskGroup)."""
    if not tb:
        return False
    markers = (
        "McpError",
        "Connection closed",
        "mcp.shared.exceptions",
        "client.initialize",
        "stdio_client",
        "pydantic_ai\\mcp.py",
        "pydantic_ai/mcp.py",
        "unhandled errors in a TaskGroup",
    )
    return any(m in tb for m in markers)


def _synthesize_ai_summary_and_steps_from_output(store: dict, event_queue: Queue | None, emit_fn) -> None:
    """No-MCP fallback: when the agent ran without tools it never calls set_ai_summary or update_ticket_status, so synthesise both from the raw output for the UI."""
    out = (store.get("output") or "").strip()
    if not out:
        return
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    issue = lines[0][:1200] if lines else ""
    work_log = " ".join(lines[1:4])[:800] if len(lines) > 1 else ""
    store["ai_summary"] = {"issue": issue, "work_log_summary": work_log}
    emit_fn(event_queue, {"kind": "ai_summary", "issue": issue, "work_log_summary": work_log})
    steps = [ln for ln in lines if ln.lstrip().startswith(("-", "*", "•", "1.", "2.", "3."))]
    if len(steps) < 2:
        steps = [ln for ln in lines[1:6] if len(ln) > 10][:5] if len(lines) > 1 else ["Diagnosis completed (no-MCP mode)."]
    summary = lines[0][:500] if lines else ""
    emit_fn(
        event_queue,
        {"kind": "technician_steps", "summary": summary, "steps": steps[:15], "steps_completed_by_ai": []},
    )

    # No-MCP mode skips the automatic DB status write, so do it here to
    # keep the UI from resetting the result on the next refresh.
    try:
        from .. import database as db

        ticket_id = store.get("ticket_id")
        if isinstance(ticket_id, int) and steps:
            store["status"] = "diagnosed"
            ok = db.update_ticket_status(
                ticket_id,
                summary or issue or "Diagnosis (no-MCP).",
                "diagnosed",
                steps[:10],
            )
            _dbg(
                "H14",
                "fallback no-mcp: update_ticket_status",
                {"ticket_id": ticket_id, "ok": ok, "steps_len": len(steps[:10])},
                run_id="post-fix",
                location="backend/agent_runner.py:_synthesize_ai_summary_and_steps_from_output",
            )
            if ok:
                emit_fn(event_queue, {"kind": "ticket_status", "ticket_id": ticket_id, "status": "diagnosed"})
    except Exception:
        _dbg(
            "H14e",
            "fallback no-mcp: update_ticket_status failed",
            {"ticket_id": store.get("ticket_id")},
            run_id="post-fix",
            location="backend/agent_runner.py:_synthesize_ai_summary_and_steps_from_output",
        )


# When the first MCP attempt fails, the retry runs without a toolset; the original prompt still mentions MCP,
# so without this suffix the model often "pretends" to call list_available_tools() and friends.
_FALLBACK_NO_MCP_SYSTEM_SUFFIX = (
    "\n\n---\n"
    "NOTE (fallback mode): in this round you have NO MCP tools and NO callable tools. "
    "Do not call list_available_tools, update_ticket_status or any other tool — they do not exist in this mode. "
    "Respond in plain text in English: diagnosis, concrete steps for the technician, and optionally what the user can check. "
    "Do not generate pseudocode or function-call syntax."
)


def _build_prompt(ticket_id: int, title: str, description: str, comments: list) -> str:
    comments_lines = [f"{c.get('author', '')}: {c.get('content', '')}" for c in (comments or [])]
    comments_text = " | ".join(comments_lines) if comments_lines else ""
    prompt_text = (
        f"Run #{ticket_id} (ticket_id={ticket_id}). Title: {title}. Description: {description}. "
        + (f"Discussion: {comments_text}. " if comments_text else "")
        + "Execute the steps from the action map in the system instructions, in the given order. "
        + "If during the run a tool is missing and you must call request_missing_tool, "
        + "describe in the note: why the current tool set is insufficient, "
        + "what this new tool would unlock for this run, what parameters/inputs it would need, "
        + "and what the expected outcome is. "
        + "Write it in a few concrete, technical sentences — no filler. "
        + "At the end, update the run status (update_ticket_status). Do not ask — act."
    )
    _dbg(
        "H_LANG_INPUT_PL",
        "built user prompt language indicators",
        {
            "title_has_pl": _looks_polish(title),
            "description_has_pl": _looks_polish(description),
            "comments_has_pl": _looks_polish(comments_text),
        },
        run_id="lang_dbg",
        location="backend/agents/runner.py:_build_prompt",
    )
    return prompt_text


def _emit(event_queue: Queue | None, payload: dict) -> None:
    """Safely push an event onto the queue (for example for SSE)."""
    if event_queue is not None:
        event_queue.put(payload)


def _dbg(hypothesis_id: str, message: str, data: dict[str, Any] | None = None, *, run_id: str = "pre-fix", location: str = "") -> None:
    # #region agent log
    try:
        root = Path(__file__).resolve().parent.parent
        paths = [root / "debug-6e6985.log", root / ".cursor" / "debug-6e6985.log"]
        payload = {
            "sessionId": "6e6985",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location or "backend/agent_runner.py",
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        line = json.dumps(payload, ensure_ascii=False) + "\n"
        for p in paths:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass
    # #endregion


def _parse_missing_tool_result(content: Any) -> dict[str, Any]:
    raw = str(content or "")
    parsed: dict[str, Any] | None = None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            parsed = obj
    except Exception:
        parsed = None
    if parsed:
        status = str(parsed.get("status") or "").strip()
        return {
            "status": status or "unknown",
            "message": str(parsed.get("message") or raw).strip(),
            "canonical_name": str(parsed.get("canonical_name") or "").strip(),
            "tool_name": str(parsed.get("tool_name") or "").strip(),
        }
    low = raw.lower()
    if "saved to backlog" in low:
        status = "created"
    elif "already exists in tool_catalog" in low:
        status = "skipped_exists_catalog"
    elif "already exists" in low and "skipping" in low:
        status = "skipped_exists_request"
    else:
        status = "unknown"
    return {"status": status, "message": raw.strip(), "canonical_name": "", "tool_name": ""}


def _pop_pending_missing_call(store: dict, tool_name: str, canonical_name: str) -> dict[str, Any] | None:
    pending = store.get("pending_missing_tool_calls") or []
    if not isinstance(pending, list):
        return None
    idx = next(
        (
            i
            for i, it in enumerate(pending)
            if isinstance(it, dict)
            and (
                (canonical_name and db.canonicalize_tool_name((it.get("tool_name") or "").strip()) == canonical_name)
                or (tool_name and db.canonicalize_tool_name((it.get("tool_name") or "").strip()) == db.canonicalize_tool_name(tool_name))
            )
        ),
        None,
    )
    if idx is None and pending:
        idx = 0
    if idx is None:
        return None
    matched = pending.pop(idx)
    store["pending_missing_tool_calls"] = pending
    return matched


def _record_missing_tool_result(store: dict, matched: dict[str, Any] | None, parsed: dict[str, Any]) -> dict[str, Any] | None:
    if not matched:
        return None
    status = str(parsed.get("status") or "unknown").strip()
    item = {
        "tool_name": matched.get("tool_name") or "",
        "reason": matched.get("reason") or "",
        "ticket_id": matched.get("ticket_id"),
        "status": status,
        "informational": status != "created",
    }
    item["canonical_name"] = db.canonicalize_tool_name(item["tool_name"])
    store.setdefault("missing_tool_requests", []).append(item)
    return item


def _infer_missing_tool_status(tool_name: str, ticket_id: int | None) -> str:
    canonical = db.canonicalize_tool_name(tool_name or "")
    if not canonical:
        return "unknown"
    try:
        catalog = db.get_tool_catalog(enabled_only=False) or []
        if any(db.canonicalize_tool_name((r.get("name") or "").strip()) == canonical for r in catalog if isinstance(r, dict)):
            return "skipped_exists_catalog"
    except Exception:
        pass
    try:
        reqs = db.get_tool_requests(ticket_id=ticket_id) if isinstance(ticket_id, int) else db.get_tool_requests()
        if any(db.canonicalize_tool_name((r.get("name") or "").strip()) == canonical for r in (reqs or []) if isinstance(r, dict)):
            return "skipped_exists_request"
    except Exception:
        pass
    return "created"


def _append_missing_tool_from_call(store: dict, tool_name: str, reason: str, ticket_id: int | None) -> dict[str, Any]:
    status = _infer_missing_tool_status(tool_name, ticket_id)
    item = {
        "tool_name": tool_name or "",
        "reason": reason or "",
        "ticket_id": ticket_id,
        "status": status,
        "informational": status != "created",
        "canonical_name": db.canonicalize_tool_name(tool_name or ""),
    }
    store.setdefault("missing_tool_requests", []).append(item)
    return item


def run_agent_sync(
    ticket_id: int,
    title: str,
    description: str,
    comments: list,
    store: dict,
    event_queue: Queue | None = None,
    *,
    flow: dict | None = None,
    approval_tools: set | list | None = None,
    system_prompt: str | None = None,
) -> None:
    """
    Runs the agent through agent.iter(); trace events go onto event_queue (SSE) and the final result is stored in `store`.
    """
    import os

    _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] run_agent_sync: entry…"})
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        store["error"] = "OPENAI_API_KEY is not set (configure it in .env or env variables)."
        store["done"] = True
        _emit(event_queue, {"kind": "sys", "text": f"[SYSTEM] Error: {store['error']}"})
        _emit(event_queue, {"done": True, "error": store["error"]})
        return

    store.setdefault("ai_summary", {"issue": "", "work_log_summary": ""})
    store.setdefault("diagnostics_entries", [])
    store.setdefault("missing_tool_requests", [])
    # Reload .env on every run (uvicorn --reload does not restart on .env changes).
    load_dotenv(_load_env_path)
    # NOTE: MCP toolset has an event-loop binding issue on Windows in this sandbox
    # (<asyncio.Lock ...> bound to a different event loop). Until MCP lifecycle is fully fixed,
    # force MCP off so "Run agent" works deterministically.
    # MCP is enabled by default. To disable MCP at runtime, set AGENT_NO_MCP_RUNTIME=1.
    use_mcp = os.environ.get("AGENT_NO_MCP_RUNTIME", "").strip().lower() not in ("1", "true", "yes")
    mode_text = "bez MCP (AGENT_NO_MCP=1)" if not use_mcp else "z MCP"
    store["trace"] = [
        {"kind": "sys", "text": "[SYSTEM] Inicjalizacja agenta…"},
        {"kind": "sys", "text": f"[SYSTEM] Tryb: {mode_text}"},
        {"kind": "sys", "text": "[SYSTEM] Uruchamianie modelu…" if not use_mcp else "[SYSTEM] Uruchamianie MCP i modelu…"},
    ]
    for e in store["trace"]:
        _emit(event_queue, e)

    _tool_progress = {
        "list_available_tools": "Fetching MCP tool list…",
        "set_ai_summary": "Preparing AI summary…",
        "ping_ip": "Checking server reachability…",
        "get_server_logs": "Pobieram logi serwera…",
        "update_ticket_status": "Updating run status…",
        "request_missing_tool": "Queuing missing-tool request…",
        "restart_service": "Czekam na zatwierdzenie restartu…",
    }
    _tool_display_names = {
        "ping_ip": "Weryfikacja sieci (ping_ip)",
        "get_server_logs": "Logi serwera (get_server_logs)",
        "update_ticket_status": "Aktualizacja statusu",
        "request_missing_tool": "Missing-tool request",
        "restart_service": "Service restart (restart_service)",
    }
    _diagnostics = store["diagnostics_entries"]

    prompt = _build_prompt(ticket_id, title, description, comments)

    agent_module.approval_state = {
        "event": threading.Event(),
        "result": None,
        "pending": None,
        "ticket_id": ticket_id,
        "ticket_title": title,
        "ticket_description": description,
        "approval_tools": set(approval_tools or []),
        "execution_id": store.get("execution_id"),
    }

    last_model_text: list[str] = []  # ostatni tekst z modelu (TextPart) – fallback dla output

    async def run_with_iter():
        nonlocal last_model_text
        try:
            if not use_mcp:
                # Text-only mode (no MCP): ask model for a JSON plan and write it directly to DB.
                from .. import database as db
                import json as _json
                import re as _re

                _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] No-MCP mode: asking the model for JSON and saving the run without tools…"})
                text_system = (
                    "You are a research assistant. MCP is disabled, so you have no tools available. "
                    "Do not call any function/tool. Return EXACTLY one JSON object.\n\n"
                    "Format:\n"
                    "{\n"
                    '  "ai_summary": {"issue": "...", "work_log_summary": "..."},\n'
                    '  "status": "in_progress" | "diagnosed",\n'
                    '  "summary": "...",\n'
                    '  "steps_taken": ["1. ...", "2. ...", "3. ..."],\n'
                    '  "missing_tools": [{"tool_name": "...", "reason": "..."}]\n'
                    "}\n\n"
                    "Rules:\n"
                    "- steps_taken must contain at least 3 concrete steps.\n"
                    "- If a tool is missing for automation, list it in missing_tools.\n"
                )

                agent = agent_module.get_agent(flow, use_mcp=False, system_prompt=text_system)
                res = await agent.run(prompt, usage_limits=_AGENT_USAGE_LIMITS)
                out_text = str(getattr(res, "output", "") or "")
                payload: dict = {}
                m = _re.search(r"\\{[\\s\\S]*\\}$", out_text.strip())
                if m:
                    try:
                        payload = _json.loads(m.group(0))
                    except Exception:
                        payload = {}
                ai_sum = payload.get("ai_summary") or {}
                store["ai_summary"] = {
                    "issue": str(ai_sum.get("issue") or "").strip(),
                    "work_log_summary": str(ai_sum.get("work_log_summary") or "").strip(),
                }
                status = str(payload.get("status") or "diagnosed").strip()
                if status not in ("in_progress", "diagnosed"):
                    status = "diagnosed"
                summary = str(payload.get("summary") or "").strip()
                if not summary:
                    summary = (out_text.strip().splitlines()[0] if out_text.strip() else "").strip()
                steps = payload.get("steps_taken") or []
                if not isinstance(steps, list):
                    steps = []
                steps = [str(s).strip() for s in steps if s and str(s).strip()]
                if len(steps) < 3:
                    steps = steps + [
                        "1. Zweryfikuj uprawnienia i zakres operacji.",
                        "2. Apply the change manually in the system (per procedure).",
                        "3. Confirm the outcome and notify the requester.",
                    ][: max(0, 3 - len(steps))]

                db.update_ticket_status(ticket_id, summary or "Diagnosis (no-MCP): no details available.", status, steps)
                _emit(event_queue, {"kind": "ticket_status", "ticket_id": ticket_id, "status": status})
                _emit(event_queue, {"kind": "technician_steps", "summary": summary, "steps": steps, "steps_completed_by_ai": []})

                missing = payload.get("missing_tools") or []
                if isinstance(missing, list):
                    for it in missing:
                        if not isinstance(it, dict):
                            continue
                        tool_name = str(it.get("tool_name") or "").strip()
                        reason = str(it.get("reason") or "").strip()
                        if tool_name:
                            store.setdefault("missing_tool_requests", []).append({"tool_name": tool_name, "reason": reason, "ticket_id": ticket_id})
                            try:
                                db.add_missing_tool_request(ticket_id, tool_name, reason or "Brak powodu.")
                            except Exception:
                                pass

                store["output"] = out_text
                return

            _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] Creating agent (MCP) in the active loop…"})
            agent = agent_module.get_agent(flow, use_mcp=use_mcp, system_prompt=system_prompt)
            _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] get_agent OK, starting model loop…"})
            async def _iterate(agent_obj):
                async with agent_obj.iter(prompt, usage_limits=_AGENT_USAGE_LIMITS) as agent_run:
                    msg = "[SYSTEM] Waiting for model response…" if not use_mcp else "[SYSTEM] MCP connection OK, waiting for model response…"
                    _emit(event_queue, {"kind": "sys", "text": msg})
                    async for node in agent_run:
                        if isinstance(node, CallToolsNode):
                            model_response = getattr(node, "model_response", None)
                            parts = getattr(model_response, "parts", None) or []
                            for part in parts:
                                if isinstance(part, TextPart):
                                    content = getattr(part, "content", None)
                                    if content and str(content).strip():
                                        last_model_text.append(str(content).strip())
                                if isinstance(part, (ToolCallPart, BuiltinToolCallPart)):
                                    args = part.args_as_dict() if part.args else {}
                                    name = part.tool_name
                                    if name != "set_ai_summary":
                                        _diagnostics.append({"tool": name, "result": "called"})
                                        _emit(event_queue, {"kind": "diagnostic", "tool": name, "result": "called"})
                                    if name == "update_ticket_status":
                                        tid = args.get("ticket_id")
                                        st = args.get("status", "")
                                        summary = args.get("summary") or ""
                                        steps_taken = args.get("steps_taken")
                                        if isinstance(steps_taken, list):
                                            steps_list = [str(s).strip() for s in steps_taken if s and str(s).strip()]
                                        elif isinstance(steps_taken, str) and steps_taken.strip():
                                            steps_list = [s.strip() for s in steps_taken.replace("\\n", "\n").split("\n") if s.strip()]
                                        else:
                                            steps_list = []
                                        entry = {"kind": "llm", "text": f'[LLM] update_ticket_status(ticket_id={tid}, status={st})'}
                                        store["trace"].append(entry)
                                        _emit(event_queue, entry)
                                        _dbg(
                                            "H_LANG_TOOL_UPDATE_STATUS",
                                            "update_ticket_status args language",
                                            {
                                                "summary_has_pl": _looks_polish(str(summary)),
                                                "steps_polish_count": sum(1 for s in steps_list if _looks_polish(str(s))),
                                                "steps_count": len(steps_list),
                                            },
                                            run_id="lang_dbg",
                                            location="backend/agents/runner.py:run_agent_sync:update_ticket_status",
                                        )
                                        if tid is not None and st:
                                            _emit(event_queue, {"kind": "ticket_status", "ticket_id": tid, "status": st})
                                        # Only count real tool returns (not our synthetic "called" markers)
                                        n_done = sum(
                                            1
                                            for e in _diagnostics
                                            if e.get("tool") != "set_ai_summary"
                                            and str(e.get("result") or "") != "called"
                                        )
                                        store["steps_completed_by_ai"] = list(range(0, min(len(steps_list), n_done)))
                                        _emit(event_queue, {"kind": "technician_steps", "summary": summary, "steps": steps_list, "steps_completed_by_ai": store["steps_completed_by_ai"]})
                                    elif name == "request_missing_tool":
                                        tool_name = (args.get("tool_name") or "").strip()
                                        reason = (args.get("reason") or "").strip()
                                        tid_missing = args.get("ticket_id")
                                        # Defer adding missing_tool_requests until we see MCP tool return.
                                        # MCP may answer that the tool already exists in tool_catalog (no-op),
                                        # but the agent can still call request_missing_tool anyway.
                                        store.setdefault("pending_missing_tool_calls", []).append(
                                            {"tool_name": tool_name, "reason": reason, "ticket_id": tid_missing}
                                        )
                                        call_item = _append_missing_tool_from_call(store, tool_name, reason, tid_missing)
                                        _emit(event_queue, {"kind": "missing_tool_request", **call_item})
                                    elif name not in ("set_ai_summary", "list_available_tools"):
                                        entry = {"kind": "llm", "text": f"[LLM] {name}(…)"}
                                        store["trace"].append(entry)
                                        _emit(event_queue, entry)
                                    if name == "set_ai_summary":
                                        store["ai_summary"] = {
                                            "issue": (args.get("issue") or "").strip(),
                                            "work_log_summary": (args.get("work_log_summary") or "").strip(),
                                        }
                                        # Keep AI Summary separate from Diagnostics to avoid duplicating content.
                                        _diagnostics.append({"tool": "set_ai_summary", "result": "OK"})
                                        _dbg(
                                            "H_LANG_TOOL_AI_SUMMARY",
                                            "set_ai_summary args language",
                                            {
                                                "issue_has_pl": _looks_polish(store["ai_summary"]["issue"]),
                                                "work_log_has_pl": _looks_polish(store["ai_summary"]["work_log_summary"]),
                                            },
                                            run_id="lang_dbg",
                                            location="backend/agents/runner.py:run_agent_sync:set_ai_summary",
                                        )
                                        _emit(event_queue, {"kind": "ai_summary", "issue": store["ai_summary"]["issue"], "work_log_summary": store["ai_summary"]["work_log_summary"]})
                        elif isinstance(node, ModelRequestNode):
                            if getattr(node, "message", None) and getattr(node.message, "parts", None):
                                for part in node.message.parts:
                                    if isinstance(part, (ToolReturnPart, BuiltinToolReturnPart)):
                                        content = getattr(part, "content", None)
                                        name = getattr(part, "tool_name", "") or ""
                                        if name and name != "set_ai_summary":
                                            if name == "request_missing_tool":
                                                parsed = _parse_missing_tool_result(content)
                                                canonical_name = parsed.get("canonical_name") or db.canonicalize_tool_name(
                                                    str(parsed.get("tool_name") or "")
                                                )
                                                matched = _pop_pending_missing_call(
                                                    store,
                                                    tool_name=str(parsed.get("tool_name") or ""),
                                                    canonical_name=str(canonical_name),
                                                )
                                                item = _record_missing_tool_result(store, matched, parsed)
                                                if item:
                                                    _emit(event_queue, {"kind": "missing_tool_request", **item})
                                                _dbg(
                                                    "H_MISSING_TOOL_RETURN_DECISION",
                                                    "request_missing_tool return processed",
                                                    {
                                                        "status": parsed.get("status"),
                                                        "matched_found": matched is not None,
                                                        "ret_preview": str(content or "")[:120],
                                                    },
                                                    run_id="mcp_decision_dbg",
                                                    location="backend/agent_runner.py:run_agent_sync:request_missing_tool",
                                                )
                                            short = _shorten_mcp_content(content)
                                            _diagnostics.append({"tool": name, "result": short})
                                            _emit(event_queue, {"kind": "diagnostic", "tool": name, "result": short})
                return agent_run

            try:
                agent_run = await _iterate(agent)
            except RuntimeError as e:
                if use_mcp and "bound to a different event loop" in str(e):
                    _emit(
                        event_queue,
                        {
                            "kind": "sys",
                            "text": "[SYSTEM] MCP error (event loop binding). Fallback: uruchamiam agenta bez MCP…",
                        },
                    )
                    agent_no_mcp = agent_module.get_agent(flow, use_mcp=False, system_prompt=system_prompt)
                    agent_run = await _iterate(agent_no_mcp)
                else:
                    raise

            # The output is only available after agent_run finishes (when End is reached).
            try:
                final = getattr(agent_run, "result", None)
                if final is not None:
                    # Pydantic AI: the final answer is result.output (not result.data).
                    out = getattr(final, "output", None)
                    if out is None:
                        out = getattr(final, "data", None)
                    if out is not None:
                        store["output"] = str(out)
            except TypeError:
                pass
            except Exception as e:
                store["error"] = str(e)
                store["trace"].append(
                    {"kind": "sys", "text": f"[SYSTEM] Result error: {traceback.format_exc()}"}
                )
                _emit(event_queue, store["trace"][-1])
            # Fallback: if result.output is empty, use the last text from the model (e.g. summary before update_ticket_status).
            if not (store.get("output") or "").strip() and last_model_text:
                store["output"] = last_model_text[-1]
            # If MCP is disabled, the model can't call update_ticket_status tool.
            # Write a best-effort ticket update directly to DB based on the final output.
            if not use_mcp:
                try:
                    from .. import database as db

                    out_txt = (store.get("output") or "").strip()
                    if out_txt:
                        lines = [ln.strip() for ln in out_txt.splitlines() if ln.strip()]
                        # Heuristic: pick a short summary from first non-empty line(s)
                        summary = lines[0][:800] if lines else "Diagnoza (bez MCP)."
                        # Heuristic: steps are bullet-like lines or fallback to generic steps
                        steps = [ln for ln in lines if ln.lstrip().startswith(("-", "*", "1.", "2.", "3."))]
                        if len(steps) < 3:
                            steps = [
                                "1. Verify permissions and access for this operation.",
                                "2. Apply the change manually in the system as requested.",
                                "3. Confirm the outcome and notify the requester.",
                            ]
                        db.update_ticket_status(ticket_id, summary, "diagnosed", steps[:10])
                        _emit(event_queue, {"kind": "ticket_status", "ticket_id": ticket_id, "status": "diagnosed"})
                except Exception:
                    pass
        except Exception as e:
            store["error"] = str(e)
            err_text = f"[SYSTEM] Error: {e}\n{traceback.format_exc()}"
            store["trace"].append({"kind": "sys", "text": err_text})
            _emit(event_queue, store["trace"][-1])

        store["done"] = True
        _emit(event_queue, {"kind": "output", "output": store.get("output") or ""})
        _emit(event_queue, {"done": True})

    AGENT_RUN_TIMEOUT = AGENT_RUN_TIMEOUT_SEC

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(asyncio.wait_for(run_with_iter(), timeout=AGENT_RUN_TIMEOUT))
    except asyncio.TimeoutError:
        store["done"] = True
        store["error"] = (
            f"Timeout ({AGENT_RUN_TIMEOUT} s): the model did not respond. "
            "Check OPENAI_API_KEY in .env, the connection to api.openai.com, and your firewall."
        )
        _emit(event_queue, {"kind": "sys", "text": f"[SYSTEM] {store['error']}"})
        _emit(event_queue, {"done": True, "error": store["error"]})
    finally:
        agent_module.approval_state = None


async def run_agent_async(
    ticket_id: int,
    title: str,
    description: str,
    comments: list,
    store: dict,
    event_queue: Queue | None = None,
    *,
    flow: dict | None = None,
    approval_tools: set | list | None = None,
    system_prompt: str | None = None,
) -> None:
    """
    Async variant of run_agent_sync.

    Runs entirely in the *current* event loop (no thread, no new loop). This avoids issues where
    asyncio primitives inside MCP toolsets are bound to a different event loop on Windows.
    """
    _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] run_agent_async: start…"})
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        store["error"] = "OPENAI_API_KEY is not set (configure it in .env or env variables)."
        store["done"] = True
        _emit(event_queue, {"kind": "sys", "text": f"[SYSTEM] Error: {store['error']}"})
        _emit(event_queue, {"done": True, "error": store["error"]})
        return

    store.setdefault("ai_summary", {"issue": "", "work_log_summary": ""})
    store.setdefault("diagnostics_entries", [])
    store.setdefault("missing_tool_requests", [])
    load_dotenv(_load_env_path)
    # MCP enabled by default; disable only when explicitly requested.
    # MCP is enabled by default. To disable MCP at runtime, set AGENT_NO_MCP_RUNTIME=1.
    use_mcp = os.environ.get("AGENT_NO_MCP_RUNTIME", "").strip().lower() not in ("1", "true", "yes")

    store["trace"] = store.get("trace") or []
    init_entries = [
        {"kind": "sys", "text": "[SYSTEM] Inicjalizacja agenta…"},
        {"kind": "sys", "text": f"[SYSTEM] Tryb: {'z MCP' if use_mcp else 'bez MCP (AGENT_NO_MCP_RUNTIME=1)'}"},
        {"kind": "sys", "text": "[SYSTEM] Uruchamianie MCP i modelu…" if use_mcp else "[SYSTEM] Uruchamianie modelu…"},
    ]
    store["trace"].extend(init_entries)
    for e in init_entries:
        _emit(event_queue, e)

    _diagnostics = store["diagnostics_entries"]
    prompt = _build_prompt(ticket_id, title, description, comments)

    # Text-only mode (no MCP): ask model for a JSON plan and write it directly to DB.
    if not use_mcp:
        from .. import database as db
        import json as _json
        import re as _re

        _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] No-MCP mode: asking the model for JSON and saving the run without tools…"})

        text_system = (
            "You are a research assistant. MCP is disabled, so you have no tools available. "
            "Do not call any function/tool. Return EXACTLY one JSON object.\n\n"
            "Required JSON format:\n"
            "{\n"
            '  "ai_summary": {"issue": "...", "work_log_summary": "..."},\n'
            '  "status": "in_progress" | "diagnosed",\n'
            '  "summary": "...",\n'
            '  "steps_taken": ["1. ...", "2. ...", "3. ..."],\n'
            '  "missing_tools": [{"tool_name": "...", "reason": "..."}]\n'
            "}\n\n"
            "Rules:\n"
            "- steps_taken must contain at least 3 concrete steps.\n"
            "- If a tool is missing for automation, list it under missing_tools.\n"
        )

        agent = agent_module.get_agent(flow, use_mcp=False, system_prompt=text_system)
        # Single-shot run (no tool calls expected)
        res = await agent.run(prompt, usage_limits=_AGENT_USAGE_LIMITS)
        out_text = str(getattr(res, "output", "") or "")
        # Extract JSON from response (robust to accidental prose). If absent/invalid, fallback to heuristics.
        payload: dict = {}
        m = _re.search(r"\\{[\\s\\S]*\\}$", out_text.strip())
        if m:
            try:
                payload = _json.loads(m.group(0))
            except Exception:
                payload = {}
        ai_sum = payload.get("ai_summary") or {}
        store["ai_summary"] = {
            "issue": str(ai_sum.get("issue") or "").strip(),
            "work_log_summary": str(ai_sum.get("work_log_summary") or "").strip(),
        }
        status = str(payload.get("status") or "diagnosed").strip()
        if status not in ("in_progress", "diagnosed"):
            status = "diagnosed"
        summary = str(payload.get("summary") or "").strip()
        if not summary:
            summary = (out_text.strip().splitlines()[0] if out_text.strip() else "").strip()
        steps = payload.get("steps_taken") or []
        if not isinstance(steps, list):
            steps = []
        steps = [str(s).strip() for s in steps if s and str(s).strip()]
        # Enforce minimum steps for technician
        if len(steps) < 3:
            steps = steps + ["1. Verify permissions and operation scope.", "2. Apply the change manually in the source system.", "3. Confirm the outcome and notify the requester."][: max(0, 3 - len(steps))]

        db.update_ticket_status(ticket_id, summary or "Diagnosis (no-MCP): no details available.", status, steps)
        _emit(event_queue, {"kind": "ticket_status", "ticket_id": ticket_id, "status": status})
        _emit(event_queue, {"kind": "technician_steps", "summary": summary, "steps": steps, "steps_completed_by_ai": []})

        missing = payload.get("missing_tools") or []
        if isinstance(missing, list):
            for it in missing:
                if not isinstance(it, dict):
                    continue
                tool_name = str(it.get("tool_name") or "").strip()
                reason = str(it.get("reason") or "").strip()
                if tool_name:
                    store.setdefault("missing_tool_requests", []).append({"tool_name": tool_name, "reason": reason, "ticket_id": ticket_id})
                    try:
                        db.add_missing_tool_request(ticket_id, tool_name, reason or "Brak powodu.")
                    except Exception:
                        pass

        store["output"] = out_text
        store["done"] = True
        _emit(event_queue, {"kind": "output", "output": out_text})
        _emit(event_queue, {"done": True})
        return

    agent_module.approval_state = {
        "event": threading.Event(),
        "result": None,
        "pending": None,
        "ticket_id": ticket_id,
        "ticket_title": title,
        "ticket_description": description,
        "approval_tools": set(approval_tools or []),
        "execution_id": store.get("execution_id"),
    }

    last_model_text: list[str] = []

    async def run_with_iter():
        nonlocal last_model_text
        try:
            _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] Creating agent (MCP) in the active loop…"})
            agent = agent_module.get_agent(flow, use_mcp=use_mcp, system_prompt=system_prompt)
            _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] get_agent OK, starting model loop…"})
            try:
                async with agent.iter(prompt, usage_limits=_AGENT_USAGE_LIMITS) as agent_run:
                    msg = "[SYSTEM] Waiting for model response…" if not use_mcp else "[SYSTEM] MCP connection OK, waiting for model response…"
                    _emit(event_queue, {"kind": "sys", "text": msg})
                    async for node in agent_run:
                        if isinstance(node, CallToolsNode):
                            model_response = getattr(node, "model_response", None)
                            parts = getattr(model_response, "parts", None) or []
                            for part in parts:
                                if isinstance(part, TextPart):
                                    content = getattr(part, "content", None)
                                    if content and str(content).strip():
                                        last_model_text.append(str(content).strip())
                                if isinstance(part, (ToolCallPart, BuiltinToolCallPart)):
                                    args = part.args_as_dict() if part.args else {}
                                    name = part.tool_name
                                    if name != "set_ai_summary":
                                        _diagnostics.append({"tool": name, "result": "called"})
                                        _emit(event_queue, {"kind": "diagnostic", "tool": name, "result": "called"})
                                    if name == "update_ticket_status":
                                        tid = args.get("ticket_id")
                                        st = args.get("status", "")
                                        summary = args.get("summary") or ""
                                        steps_taken = args.get("steps_taken")
                                        if isinstance(steps_taken, list):
                                            steps_list = [str(s).strip() for s in steps_taken if s and str(s).strip()]
                                        elif isinstance(steps_taken, str) and steps_taken.strip():
                                            steps_list = [s.strip() for s in steps_taken.replace("\\n", "\n").split("\n") if s.strip()]
                                        else:
                                            steps_list = []
                                        entry = {"kind": "llm", "text": f'[LLM] update_ticket_status(ticket_id={tid}, status={st})'}
                                        store["trace"].append(entry)
                                        _emit(event_queue, entry)
                                        _dbg(
                                            "H_LANG_TOOL_UPDATE_STATUS_ASYNC",
                                            "update_ticket_status args language (async)",
                                            {
                                                "summary_has_pl": _looks_polish(str(summary)),
                                                "steps_polish_count": sum(1 for s in steps_list if _looks_polish(str(s))),
                                                "steps_count": len(steps_list),
                                            },
                                            run_id="lang_dbg",
                                            location="backend/agents/runner.py:run_agent_async:update_ticket_status",
                                        )
                                        if tid is not None and st:
                                            _emit(event_queue, {"kind": "ticket_status", "ticket_id": tid, "status": st})
                                        # Only count real tool returns (not our synthetic "called" markers)
                                        n_done = sum(
                                            1
                                            for e in _diagnostics
                                            if e.get("tool") != "set_ai_summary"
                                            and str(e.get("result") or "") != "called"
                                        )
                                        store["steps_completed_by_ai"] = list(range(0, min(len(steps_list), n_done)))
                                        _emit(event_queue, {"kind": "technician_steps", "summary": summary, "steps": steps_list, "steps_completed_by_ai": store["steps_completed_by_ai"]})
                                    elif name == "request_missing_tool":
                                        tool_name = (args.get("tool_name") or "").strip()
                                        reason = (args.get("reason") or "").strip()
                                        tid_missing = args.get("ticket_id")
                                        store.setdefault("pending_missing_tool_calls", []).append(
                                            {"tool_name": tool_name, "reason": reason, "ticket_id": tid_missing}
                                        )
                                        call_item = _append_missing_tool_from_call(store, tool_name, reason, tid_missing)
                                        _emit(event_queue, {"kind": "missing_tool_request", **call_item})
                                    elif name == "set_ai_summary":
                                        store["ai_summary"] = {
                                            "issue": (args.get("issue") or "").strip(),
                                            "work_log_summary": (args.get("work_log_summary") or "").strip(),
                                        }
                                        # Keep AI Summary separate from Diagnostics to avoid duplicating content.
                                        _diagnostics.append({"tool": "set_ai_summary", "result": "OK"})
                                        _dbg(
                                            "H_LANG_TOOL_AI_SUMMARY_ASYNC",
                                            "set_ai_summary args language (async)",
                                            {
                                                "issue_has_pl": _looks_polish(store["ai_summary"]["issue"]),
                                                "work_log_has_pl": _looks_polish(store["ai_summary"]["work_log_summary"]),
                                            },
                                            run_id="lang_dbg",
                                            location="backend/agents/runner.py:run_agent_async:set_ai_summary",
                                        )
                                        _emit(event_queue, {"kind": "ai_summary", "issue": store["ai_summary"]["issue"], "work_log_summary": store["ai_summary"]["work_log_summary"]})
                                    else:
                                        if name not in ("set_ai_summary", "list_available_tools"):
                                            entry = {"kind": "llm", "text": f"[LLM] {name}(…)"}
                                            store["trace"].append(entry)
                                            _emit(event_queue, entry)
                        elif isinstance(node, ModelRequestNode):
                            if getattr(node, "message", None) and getattr(node.message, "parts", None):
                                for part in node.message.parts:
                                    if isinstance(part, (ToolReturnPart, BuiltinToolReturnPart)):
                                        content = getattr(part, "content", None)
                                        name = getattr(part, "tool_name", "") or ""
                                        if name and name != "set_ai_summary":
                                            if name == "request_missing_tool":
                                                parsed = _parse_missing_tool_result(content)
                                                canonical_name = parsed.get("canonical_name") or db.canonicalize_tool_name(
                                                    str(parsed.get("tool_name") or "")
                                                )
                                                matched = _pop_pending_missing_call(
                                                    store,
                                                    tool_name=str(parsed.get("tool_name") or ""),
                                                    canonical_name=str(canonical_name),
                                                )
                                                item = _record_missing_tool_result(store, matched, parsed)
                                                if item:
                                                    _emit(event_queue, {"kind": "missing_tool_request", **item})
                                                _dbg(
                                                    "H_MISSING_TOOL_RETURN_DECISION",
                                                    "request_missing_tool return processed",
                                                    {
                                                        "status": parsed.get("status"),
                                                        "matched_found": matched is not None,
                                                        "ret_preview": str(content or "")[:120],
                                                    },
                                                    run_id="mcp_decision_dbg",
                                                    location="backend/agent_runner.py:run_agent_async:model_request:request_missing_tool",
                                                )
                                            short = _shorten_mcp_content(content)
                                            _diagnostics.append({"tool": name, "result": short})
                                            _emit(event_queue, {"kind": "diagnostic", "tool": name, "result": short})
            except RuntimeError as e:
                if use_mcp and "bound to a different event loop" in str(e):
                    _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] MCP error (event loop binding). Fallback: uruchamiam agenta bez MCP…"})
                    agent2 = agent_module.get_agent(flow, use_mcp=False, system_prompt=system_prompt)
                    async with agent2.iter(prompt, usage_limits=_AGENT_USAGE_LIMITS) as agent_run:
                        _emit(event_queue, {"kind": "sys", "text": "[SYSTEM] No-MCP mode: waiting for model response…"})
                        async for _ in agent_run:
                            pass
                else:
                    raise

            try:
                final = getattr(agent_run, "result", None)
                if final is not None:
                    out = getattr(final, "output", None)
                    if out is None:
                        out = getattr(final, "data", None)
                    if out is not None:
                        store["output"] = str(out)
            except TypeError:
                pass
            except Exception as e:
                store["error"] = str(e)
                store["trace"].append({"kind": "sys", "text": f"[SYSTEM] Result error: {traceback.format_exc()}"})
                _emit(event_queue, store["trace"][-1])
            if not (store.get("output") or "").strip() and last_model_text:
                store["output"] = last_model_text[-1]
            _dbg(
                "H_LANG_FINAL_OUTPUT_ASYNC",
                "final output language (async)",
                {"output_has_pl": _looks_polish(str(store.get("output") or "")), "output_len": len(str(store.get("output") or ""))},
                run_id="lang_dbg",
                location="backend/agents/runner.py:run_agent_async:final_output",
            )
        except Exception as e:
            store["error"] = str(e)
            err_text = f"[SYSTEM] Error: {e}\n{traceback.format_exc()}"
            store.setdefault("trace", []).append({"kind": "sys", "text": err_text})
            _emit(event_queue, store["trace"][-1])
        store["done"] = True
        _emit(event_queue, {"kind": "output", "output": store.get("output") or ""})
        _emit(event_queue, {"done": True})

    AGENT_RUN_TIMEOUT = AGENT_RUN_TIMEOUT_SEC
    try:
        await asyncio.wait_for(run_with_iter(), timeout=AGENT_RUN_TIMEOUT)
    except asyncio.TimeoutError:
        store["done"] = True
        store["error"] = (
            f"Timeout ({AGENT_RUN_TIMEOUT} s): the model did not respond. "
            "Check OPENAI_API_KEY in .env, the connection to api.openai.com, and your firewall."
        )
        _emit(event_queue, {"kind": "sys", "text": f"[SYSTEM] {store['error']}"})
        _emit(event_queue, {"done": True, "error": store["error"]})
    finally:
        agent_module.approval_state = None


async def run_single_node_async(
    ticket_id: int,
    title: str,
    description: str,
    comments: list,
    node_system_prompt: str,
    max_retry: int,
    store: dict,
    event_queue: Queue | None,
    *,
    flow: dict | None = None,
    approval_tools: set | list | None = None,
    use_mcp: bool = True,
    emit_fn=None,
    model_spec: str | None = None,
    max_tokens: int | None = None,
) -> None:
    """
    Run one flow node (single LLM call with tools). Used by flow_engine step-by-step.
    max_retry from flow_definitions is passed in prompt; store/event_queue updated as in full run.
    """
    if emit_fn is None:
        emit_fn = _emit
    _diagnostics = store.setdefault("diagnostics_entries", [])
    last_model_text: list[str] = []
    comments_lines = [f"{c.get('author', '')}: {c.get('content', '')}" for c in (comments or [])]
    comments_text = " | ".join(comments_lines) if comments_lines else ""
    user_prompt = (
        f"Run #{ticket_id}. Title: {title}. Description: {description}. "
        + (f"Discussion: {comments_text}. " if comments_text else "")
        + f"Execute exactly this single step from the system instructions. Maximum {max_retry} iterations."
    )
    agent_module.approval_state = {
        "event": threading.Event(),
        "result": None,
        "pending": None,
        "ticket_id": ticket_id,
        "ticket_title": title,
        "ticket_description": description,
        "approval_tools": set(approval_tools or []),
        "execution_id": store.get("execution_id"),
    }

    async def _consume_iter(agent_obj) -> None:
        async with agent_obj.iter(user_prompt, usage_limits=_AGENT_USAGE_LIMITS) as agent_run:
            async for node in agent_run:
                if isinstance(node, CallToolsNode):
                    model_response = getattr(node, "model_response", None)
                    parts = getattr(model_response, "parts", None) or []
                    for part in parts:
                        if isinstance(part, TextPart):
                            content = getattr(part, "content", None)
                            if content and str(content).strip():
                                last_model_text.append(str(content).strip())
                        if isinstance(part, (ToolCallPart, BuiltinToolCallPart)):
                            args = part.args_as_dict() if part.args else {}
                            name = part.tool_name

                            # #region agent log
                            if name in ("update_ticket_status", "request_missing_tool", "list_available_tools", "set_ai_summary"):
                                store.setdefault("_tool_call_counts", {})
                                store["_tool_call_counts"][name] = store["_tool_call_counts"].get(name, 0) + 1
                                call_idx = store["_tool_call_counts"][name]
                                # Avoid logging raw args content (may contain user data).
                                _dbg(
                                    "H_REPEAT_TOOLS",
                                    "single node: tool called (counted)",
                                    {
                                        "tool": name,
                                        "count": call_idx,
                                        "arg_keys": list(args.keys())[:8] if isinstance(args, dict) else [],
                                    },
                                    run_id="tool_seq_dbg",
                                    location="backend/agent_runner.py:run_single_node_async:tool_call",
                                )
                            # #endregion

                            if name != "set_ai_summary":
                                _diagnostics.append({"tool": name, "result": "called"})
                                emit_fn(event_queue, {"kind": "diagnostic", "tool": name, "result": "called"})
                            if name == "update_ticket_status":
                                tid = args.get("ticket_id")
                                st = args.get("status", "")
                                summary = args.get("summary") or ""
                                steps_taken = args.get("steps_taken")
                                if isinstance(steps_taken, list):
                                    steps_list = [str(s).strip() for s in steps_taken if s and str(s).strip()]
                                elif isinstance(steps_taken, str) and steps_taken.strip():
                                    steps_list = [s.strip() for s in steps_taken.replace("\\n", "\n").split("\n") if s.strip()]
                                else:
                                    steps_list = []
                                if st:
                                    store["status"] = st
                                emit_fn(event_queue, {"kind": "llm", "text": f'[LLM] update_ticket_status(ticket_id={tid}, status={st})'})
                                if tid is not None and st:
                                    emit_fn(event_queue, {"kind": "ticket_status", "ticket_id": tid, "status": st})
                                n_done = sum(1 for e in _diagnostics if e.get("tool") != "set_ai_summary" and str(e.get("result") or "") != "called")
                                store["steps_completed_by_ai"] = list(range(0, min(len(steps_list), n_done)))
                                emit_fn(event_queue, {"kind": "technician_steps", "summary": summary, "steps": steps_list, "steps_completed_by_ai": store.get("steps_completed_by_ai", [])})
                            elif name == "request_missing_tool":
                                tool_name = (args.get("tool_name") or "").strip()
                                reason = (args.get("reason") or "").strip()
                                tid_missing = args.get("ticket_id")
                                # Defer adding missing_tool_requests until we see the MCP tool return.
                                # MCP can return a "not adding a missing-tool request" message when the tool
                                # exists in tool_catalog; that should not show up in UI as missing.
                                store.setdefault("pending_missing_tool_calls", []).append(
                                    {"tool_name": tool_name, "reason": reason, "ticket_id": tid_missing}
                                )
                                call_item = _append_missing_tool_from_call(store, tool_name, reason, tid_missing)
                                emit_fn(event_queue, {"kind": "missing_tool_request", **call_item})
                                _dbg(
                                    "H_MISSING_PENDING_APPEND",
                                    "pending missing-tool call appended",
                                    {
                                        "tool_name": tool_name,
                                        "ticket_id": tid_missing,
                                        "pending_len": len(store.get("pending_missing_tool_calls") or []),
                                    },
                                    run_id="mcp_visibility_dbg",
                                    location="backend/agent_runner.py:run_single_node_async:pending_append",
                                )
                                # #region agent log
                                _dbg(
                                    "H_REPEAT_TOOLS2",
                                    "single node: request_missing_tool payload snapshot",
                                    {
                                        "tool_name": tool_name,
                                        "reason_len": len(reason),
                                        "ticket_id": tid_missing,
                                    },
                                    run_id="tool_seq_dbg",
                                    location="backend/agent_runner.py:run_single_node_async:request_missing_tool",
                                )
                                # #endregion
                                # Emit missing_tool_request only after we see the tool return.
                            elif name == "set_ai_summary":
                                store["ai_summary"] = {"issue": (args.get("issue") or "").strip(), "work_log_summary": (args.get("work_log_summary") or "").strip()}
                                _diagnostics.append({"tool": "set_ai_summary", "result": "OK"})
                                emit_fn(event_queue, {"kind": "ai_summary", "issue": store["ai_summary"]["issue"], "work_log_summary": store["ai_summary"]["work_log_summary"]})
                            elif name not in ("set_ai_summary", "list_available_tools"):
                                emit_fn(event_queue, {"kind": "llm", "text": f"[LLM] {name}(…)"})
                elif isinstance(node, ModelRequestNode):
                    if getattr(node, "message", None) and getattr(node.message, "parts", None):
                        for part in node.message.parts:
                            if isinstance(part, TextPart):
                                content = getattr(part, "content", None)
                                if content and str(content).strip():
                                    last_model_text.append(str(content).strip())
                            elif isinstance(part, (ToolReturnPart, BuiltinToolReturnPart)):
                                content = getattr(part, "content", None)
                                name = getattr(part, "tool_name", "") or ""
                                _dbg(
                                    "H_MISSING_RETURN_PART",
                                    "model request tool return part seen",
                                    {
                                        "part_type": type(part).__name__,
                                        "tool_name": name,
                                        "has_content": content is not None,
                                        "content_preview": str(content or "")[:80],
                                    },
                                    run_id="mcp_visibility_dbg",
                                    location="backend/agent_runner.py:run_single_node_async:model_request:return_part",
                                )
                                if name and name != "set_ai_summary":
                                    if name == "request_missing_tool":
                                        parsed = _parse_missing_tool_result(content)
                                        canonical_name = parsed.get("canonical_name") or db.canonicalize_tool_name(
                                            str(parsed.get("tool_name") or "")
                                        )
                                        matched = _pop_pending_missing_call(
                                            store,
                                            tool_name=str(parsed.get("tool_name") or ""),
                                            canonical_name=str(canonical_name),
                                        )
                                        item = _record_missing_tool_result(store, matched, parsed)
                                        if item:
                                            emit_fn(event_queue, {"kind": "missing_tool_request", **item})
                                        _dbg(
                                            "H_MISSING_ITEM_RECORD",
                                            "missing-tool item record decision",
                                            {
                                                "item_added": item is not None,
                                                "store_missing_len": len(store.get("missing_tool_requests") or []),
                                                "parsed_status": parsed.get("status"),
                                            },
                                            run_id="mcp_visibility_dbg",
                                            location="backend/agent_runner.py:run_single_node_async:item_record",
                                        )
                                        _dbg(
                                            "H_MISSING_TOOL_RETURN_DECISION",
                                            "request_missing_tool return processed",
                                            {
                                                "status": parsed.get("status"),
                                                "matched_found": matched is not None,
                                                "ret_preview": str(content or "")[:120],
                                            },
                                            run_id="mcp_decision_dbg",
                                            location="backend/agent_runner.py:run_single_node_async:model_request:request_missing_tool",
                                        )
                                    else:
                                        _dbg(
                                            "H_MISSING_RETURN_OTHER_TOOL",
                                            "tool return skipped for missing-tool mapping (different tool_name)",
                                            {"tool_name": name},
                                            run_id="mcp_visibility_dbg",
                                            location="backend/agent_runner.py:run_single_node_async:model_request:return_other_tool",
                                        )
                                    short = _shorten_mcp_content(content)
                                    _diagnostics.append({"tool": name, "result": short})
                                    emit_fn(event_queue, {"kind": "diagnostic", "tool": name, "result": short})
        try:
            final = getattr(agent_run, "result", None)
            if final is not None:
                out = getattr(final, "output", None) or getattr(final, "data", None)
                if out is not None:
                    store["output"] = str(out)
        except (TypeError, Exception):
            pass
        if not (store.get("output") or "").strip() and last_model_text:
            store["output"] = last_model_text[-1]

    try:
        _dbg(
            "H1",
            "run_single_node_async start",
            {"use_mcp": use_mcp, "max_retry": max_retry, "model_spec": model_spec},
            location="backend/agent_runner.py:run_single_node_async:start",
        )
        # Keep this stage string free of user/ticket content (it may be exposed in watchdog error).
        store["last_stage"] = "run_single_node_async:before_agent_iter"
        agent = agent_module.get_agent(
            flow,
            use_mcp=use_mcp,
            system_prompt=node_system_prompt,
            model_spec=model_spec,
            max_tokens=max_tokens,
        )
        _dbg(
            "H2",
            "agent created; entering agent.iter",
            {"use_mcp": use_mcp},
            location="backend/agent_runner.py:run_single_node_async:before_iter",
        )
        store["last_stage"] = "run_single_node_async:agent_iter"
        await _consume_iter(agent)
    except BaseException as e:
        tb = traceback.format_exc()
        tb_mcp = _traceback_indicates_mcp_init_failure(tb)
        _dbg(
            "H3",
            "run_single_node_async exception",
            {
                "exc_type": type(e).__name__,
                "exc_str": str(e)[:500],
                "use_mcp": use_mcp,
                "tb_has_mcp": tb_mcp,
            },
            location="backend/agent_runner.py:run_single_node_async:except",
        )
        mcp_recoverable = bool(use_mcp and tb_mcp)
        if mcp_recoverable:
            _dbg(
                "H4",
                "mcp init failure — retry without MCP",
                {"first_exc": type(e).__name__},
                run_id="post-fix",
                location="backend/agent_runner.py:run_single_node_async:mcp_fallback",
            )
            emit_fn(
                event_queue,
                {
                    "kind": "sys",
                    "text": "[SYSTEM] MCP: connection or initialisation error (stdio). Retrying this step without MCP tools…",
                },
            )
            try:
                agent_plain = agent_module.get_agent(
                    flow,
                    use_mcp=False,
                    system_prompt=node_system_prompt + _FALLBACK_NO_MCP_SYSTEM_SUFFIX,
                    model_spec=model_spec,
                    max_tokens=max_tokens,
                )
                await _consume_iter(agent_plain)
                _synthesize_ai_summary_and_steps_from_output(store, event_queue, emit_fn)
                _dbg(
                    "H4b",
                    "mcp fallback completed without exception",
                    {},
                    run_id="post-fix",
                    location="backend/agent_runner.py:run_single_node_async:mcp_fallback_ok",
                )
            except BaseException as e2:
                tb2 = traceback.format_exc()
                _dbg(
                    "H5",
                    "mcp fallback failed",
                    {"exc_type": type(e2).__name__, "exc_str": str(e2)[:500]},
                    run_id="post-fix",
                    location="backend/agent_runner.py:run_single_node_async:mcp_fallback_err",
                )
                if isinstance(e2, Exception):
                    store["error"] = str(e2)
                    store.setdefault("trace", []).append({"kind": "sys", "text": f"[SYSTEM] Node error (no MCP): {tb2}"})
                    emit_fn(event_queue, store["trace"][-1])
                else:
                    raise
        else:
            from .simple_runner import is_context_overflow_error, resolve_overflow_model_spec

            overflow_spec = resolve_overflow_model_spec() if is_context_overflow_error(e) else None
            if overflow_spec and overflow_spec != model_spec:
                emit_fn(
                    event_queue,
                    {
                        "kind": "sys",
                        "text": (
                            f"[SYSTEM] Node: context overflow on {model_spec or 'default'}; "
                            f"retrying with overflow model {overflow_spec}."
                        ),
                    },
                )
                try:
                    agent_overflow = agent_module.get_agent(
                        flow,
                        use_mcp=use_mcp,
                        system_prompt=node_system_prompt,
                        model_spec=overflow_spec,
                        max_tokens=max_tokens,
                    )
                    await _consume_iter(agent_overflow)
                    _dbg(
                        "H4c",
                        "overflow fallback completed without exception",
                        {"overflow_spec": overflow_spec},
                        run_id="post-fix",
                        location="backend/agent_runner.py:run_single_node_async:overflow_fallback_ok",
                    )
                except BaseException as e3:
                    tb3 = traceback.format_exc()
                    _dbg(
                        "H5b",
                        "overflow fallback failed",
                        {"exc_type": type(e3).__name__, "exc_str": str(e3)[:500]},
                        run_id="post-fix",
                        location="backend/agent_runner.py:run_single_node_async:overflow_fallback_err",
                    )
                    if isinstance(e3, Exception):
                        store["error"] = str(e3)
                        store.setdefault("trace", []).append(
                            {"kind": "sys", "text": f"[SYSTEM] Node error (overflow fallback): {tb3}"}
                        )
                        emit_fn(event_queue, store["trace"][-1])
                    else:
                        raise
            elif isinstance(e, Exception):
                store["error"] = str(e)
                store.setdefault("trace", []).append({"kind": "sys", "text": f"[SYSTEM] Node error: {tb}"})
                emit_fn(event_queue, store["trace"][-1])
            else:
                raise
    finally:
        agent_module.approval_state = None
