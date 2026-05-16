"""
Builder/Developer Agent flow: implement missing tools requested by operational agent.

Exposed via API endpoint: POST /api/tools/requested/{id}/reserve
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from .. import database as db

# Load tokens from repo root (.env) or backend/.env (fallback)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# override=True: uvicorn --reload and IDE shells often leave env vars set (sometimes empty),
# and with the default override=False the values from the .env file would be ignored.
load_dotenv(_PROJECT_ROOT / ".env", override=True)
load_dotenv(_PROJECT_ROOT / "backend" / ".env", override=True)

SIMILARITY_THRESHOLD = 0.85

_GENERATED_TOOLS_DIR = _PROJECT_ROOT / "backend" / "tools" / "generated"
_TOOLS_REPO_ROOT = Path(os.environ.get("TOOLS_REPO_ROOT") or (_PROJECT_ROOT.parent / "geneguidelines-tools"))
_TOOLS_REPO_TOOLS_DIR = _TOOLS_REPO_ROOT / "tools"


def _tools_dbg(hypothesis_id: str, message: str, data: dict[str, Any] | None = None, *, run_id: str = "builder", location: str = "") -> None:
    """
    Builder/runtime diagnostics for tool PR creation.
    Writes NDJSON into the same debug-6e6985.log used by agent/flow logs.
    """
    try:
        root = Path(__file__).resolve().parent.parent.parent
        paths = [root / "debug-6e6985.log", root / ".cursor" / "debug-6e6985.log"]
        payload = {
            "sessionId": "6e6985",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location or "backend/agent_tools.py",
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


def _tools_repo_is_available() -> bool:
    return _TOOLS_REPO_ROOT.exists() and (_TOOLS_REPO_ROOT / ".git").exists() and _TOOLS_REPO_TOOLS_DIR.exists()


def _similarity_score(a: str, b: str) -> float:
    return SequenceMatcher(a=(a or "").lower().strip(), b=(b or "").lower().strip()).ratio()


def _find_similar_tools(query: str, threshold: float = SIMILARITY_THRESHOLD) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return {"matches": []}
    catalog = db.get_tool_catalog(enabled_only=False)
    impl = db.get_tool_implementations()
    matches: list[dict[str, Any]] = []
    for r in catalog:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        s = _similarity_score(q, name)
        if s >= threshold:
            matches.append({"name": name, "score": round(s, 3), "source": "tool_catalog"})
    for r in impl:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        s = _similarity_score(q, name)
        if s >= threshold:
            matches.append({"name": name, "score": round(s, 3), "source": "tool_implementations"})
    matches.sort(key=lambda m: m["score"], reverse=True)
    return {"matches": matches[:10]}


_PL_TO_ASCII = str.maketrans(
    "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ",
    "acelnoszzACELNOSZZ",
)


def _to_ascii_safe(text: str) -> str:
    if not text:
        return ""
    s = text.translate(_PL_TO_ASCII)
    return s.encode("ascii", "replace").decode("ascii").replace("?", "_")


def _to_tool_function_name(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "new_tool"
    if s[0].isdigit():
        s = f"tool_{s}"
    return s


def _ensure_tool_in_operational_mcp(tool_name: str, note: str) -> dict[str, Any]:
    func_name = _to_tool_function_name(tool_name)
    _GENERATED_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    module_path = _GENERATED_TOOLS_DIR / f"{func_name}.py"
    tools_repo_path = _TOOLS_REPO_TOOLS_DIR / f"{func_name}.py" if _tools_repo_is_available() else None

    init_py = _GENERATED_TOOLS_DIR / "__init__.py"
    if not init_py.exists():
        init_py.write_text("# generated tools package\n", encoding="utf-8")

    if module_path.exists():
        catalog_id = db.add_tool_to_catalog(
            name=func_name,
            category="General",
            execution_mode="auto",
            scope="operational",
            enabled=1,
        )
        # Best-effort mirror into the Tools repo (if present).
        if tools_repo_path is not None and not tools_repo_path.exists():
            try:
                tools_repo_path.write_text(module_path.read_text(encoding="utf-8"), encoding="utf-8")
            except Exception:
                pass
        return {
            "ok": True,
            "already_exists": True,
            "func_name": func_name,
            "path": str(module_path),
            "tools_repo_path": str(tools_repo_path) if tools_repo_path is not None else None,
            "catalog_id": catalog_id,
        }

    tool_name_ascii = _to_ascii_safe(tool_name)
    doc_note = _to_ascii_safe((note or "").strip()).replace('"""', "'") or "(none)"
    tool_src = f"""from __future__ import annotations

import json
import os
from typing import Any


def register(mcp: Any) -> None:
    @mcp.tool()
    def {func_name}(payload: str) -> str:
        \"\"\"Auto-generated tool from tool_request.

        Request name: {tool_name_ascii}
        Note: {doc_note}

        Integration hint: real implementation should use env-based config
        (base URL, auth token), validate input, and resolve any identifiers by
        name/email before performing mutations.

        Payload convention (recommended): JSON string with the fields this
        tool needs (validated below). The strict-mode envelope is returned
        when ``TOOL_STUB_STRICT`` is set, otherwise a deterministic mock
        success is returned so the calling flow can proceed.
        \"\"\"
        # IMPORTANT CONTRACT:
        # Always return a JSON string with fields:
        # ok, status(success|partial|error), message, result, errors, missing.
        if not payload or not str(payload).strip():
            return json.dumps(
                {{
                    "ok": False,
                    "status": "error",
                    "message": "payload is required (JSON string)",
                    "result": None,
                    "missing": ["payload"],
                    "errors": ["payload is required (JSON string)"],
                }},
                ensure_ascii=False,
            )
        raw = str(payload).strip()
        try:
            obj = json.loads(raw) if raw.startswith("{{") and raw.endswith("}}") else json.loads(raw)
        except Exception as e:
            return json.dumps(
                {{
                    "ok": False,
                    "status": "error",
                    "message": f"invalid_json: {{type(e).__name__}}",
                    "result": None,
                    "missing": [],
                    "errors": [f"invalid_json: {{type(e).__name__}}"],
                }},
                ensure_ascii=False,
            )
        users = obj.get("users")
        group = obj.get("group")
        mode = (obj.get("mode") or "").strip().lower()
        missing: list[str] = []
        if not users:
            missing.append("users")
        if not group:
            missing.append("group")
        if mode not in ("add", "remove"):
            missing.append("mode(add|remove)")
        if missing:
            return json.dumps(
                {{
                    "ok": False,
                    "status": "error",
                    "message": "missing_required_fields",
                    "result": None,
                    "missing": missing,
                    "errors": ["missing_required_fields"],
                }},
                ensure_ascii=False,
            )
        strict_mode = (os.environ.get("TOOL_STUB_STRICT") or "").strip().lower() in ("1", "true", "yes", "on")
        if strict_mode:
            return json.dumps(
                {{
                    "ok": False,
                    "status": "error",
                    "message": "stub strict mode enabled: real integration is not implemented",
                    "result": {{
                        "tool": "{func_name}",
                        "mode": mode,
                        "group": group,
                        "requested": users,
                        "changed": [],
                        "skipped": users,
                    }},
                    "missing": [],
                    "errors": ["stub_tool_strict_mode: integration not implemented"],
                }},
                ensure_ascii=False,
            )
        # STUB behaviour (replace with the real integration when implemented):
        # Return a deterministic result so the calling agent can make a decision
        # without re-requesting the same tool.
        return json.dumps(
            {{
                "ok": True,
                "status": "success",
                "message": "mock success: tool executed in sandbox mode",
                "result": {{
                    "tool": "{func_name}",
                    "mode": mode,
                    "group": group,
                    "requested": users,
                    "changed": users,
                    "skipped": [],
                }},
                "missing": [],
                "errors": [],
            }},
            ensure_ascii=False,
        )
"""
    module_path.write_text(tool_src, encoding="utf-8")
    if tools_repo_path is not None:
        try:
            tools_repo_path.write_text(tool_src, encoding="utf-8")
        except Exception:
            pass
    catalog_id = db.add_tool_to_catalog(
        name=func_name,
        category="General",
        execution_mode="auto",
        scope="operational",
        enabled=1,
    )
    return {
        "ok": True,
        "func_name": func_name,
        "path": str(module_path),
        "tools_repo_path": str(tools_repo_path) if tools_repo_path is not None else None,
        "catalog_id": catalog_id,
    }


def _git(args: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    try:
        p = subprocess.run(
            ["git", *args],
            cwd=str(cwd or _PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        return {"ok": p.returncode == 0, "code": p.returncode, "out": p.stdout, "err": p.stderr, "args": args}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "args": args}


def _git_is_repo() -> bool:
    r = _git(["rev-parse", "--is-inside-work-tree"], cwd=_PROJECT_ROOT)
    return bool(r.get("ok")) and "true" in (r.get("out") or "").lower()


def _git_is_tools_repo() -> bool:
    if not _TOOLS_REPO_ROOT.exists():
        return False
    r = _git(["rev-parse", "--is-inside-work-tree"], cwd=_TOOLS_REPO_ROOT)
    return bool(r.get("ok")) and "true" in (r.get("out") or "").lower()


def _get_github_token() -> str:
    return (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()


def _get_origin_owner_repo() -> tuple[str, str] | None:
    # Default: sandbox repo. Tools repo has its own remote (used for tool PRs).
    rem = _git(["remote", "get-url", "origin"], cwd=_PROJECT_ROOT)
    if not rem.get("ok"):
        return None
    url = (rem.get("out") or "").strip()
    m = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)", url)
    if not m:
        return None
    return m.group("owner"), m.group("repo")


def _get_tools_origin_owner_repo() -> tuple[str, str] | None:
    if not _git_is_tools_repo():
        return None
    rem = _git(["remote", "get-url", "origin"], cwd=_TOOLS_REPO_ROOT)
    if not rem.get("ok"):
        return None
    url = (rem.get("out") or "").strip()
    m = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)", url)
    if not m:
        return None
    return m.group("owner"), m.group("repo")


def _git_push_with_token(branch_name: str) -> dict[str, Any]:
    """
    Push branch to origin using GITHUB_TOKEN/ GH_TOKEN (non-interactive).
    Does not persist token to git config.
    """
    token = _get_github_token()
    if not token:
        return {"ok": False, "reason": "missing_token"}
    rem = _git(["remote", "get-url", "origin"])
    if not rem.get("ok"):
        return {"ok": False, "reason": "no_origin_remote", "err": rem.get("err"), "out": rem.get("out")}
    url = (rem.get("out") or "").strip()
    if "github.com" not in url:
        return {"ok": False, "reason": "origin_not_github", "origin": url}
    # Convert to https URL
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.split(":", 1)[1]
    if url.startswith("https://github.com/") and not url.endswith(".git"):
        url += ".git"
    auth_url = url.replace("https://github.com/", f"https://x-access-token:{token}@github.com/")
    try:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        p = subprocess.run(
            ["git", "push", "-u", auth_url, branch_name],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        out = (p.stdout or "").replace(token, "***")
        err = (p.stderr or "").replace(token, "***")
        # IMPORTANT: never return args containing the tokenized URL
        return {
            "ok": p.returncode == 0,
            "code": p.returncode,
            "out": out,
            "err": err,
            "args": ["push", "-u", "origin(<token>)", branch_name],
        }
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}", "args": ["push", "-u", "origin(<token>)", branch_name]}


def _git_push_with_token_tools(branch_name: str) -> dict[str, Any]:
    """Push branch to Tools repo using GITHUB_TOKEN/ GH_TOKEN (non-interactive)."""
    token = _get_github_token()
    if not token:
        return {"ok": False, "reason": "missing_token"}
    if not _git_is_tools_repo():
        return {"ok": False, "reason": "tools_repo_not_available", "tools_repo": str(_TOOLS_REPO_ROOT)}
    rem = _git(["remote", "get-url", "origin"], cwd=_TOOLS_REPO_ROOT)
    if not rem.get("ok"):
        return {"ok": False, "reason": "no_origin_remote", "err": rem.get("err"), "out": rem.get("out")}
    url = (rem.get("out") or "").strip()
    if "github.com" not in url:
        return {"ok": False, "reason": "origin_not_github", "origin": url}
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.split(":", 1)[1]
    if url.startswith("https://github.com/") and not url.endswith(".git"):
        url += ".git"
    auth_url = url.replace("https://github.com/", f"https://x-access-token:{token}@github.com/")
    try:
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        p = subprocess.run(
            ["git", "push", "-u", auth_url, branch_name],
            cwd=str(_TOOLS_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        out = (p.stdout or "").replace(token, "***")
        err = (p.stderr or "").replace(token, "***")
        return {
            "ok": p.returncode == 0,
            "code": p.returncode,
            "out": out,
            "err": err,
            "args": ["push", "-u", "origin(<token>)", branch_name],
        }
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}", "args": ["push", "-u", "origin(<token>)", branch_name]}


def _git_remote_branch_exists_tools(branch_name: str) -> dict[str, Any]:
    """Check if branch already exists on origin in Tools repo."""
    if not _git_is_tools_repo():
        return {"ok": False, "reason": "tools_repo_not_available"}
    res = _git(["ls-remote", "--heads", "origin", branch_name], cwd=_TOOLS_REPO_ROOT)
    if not res.get("ok"):
        return {"ok": False, "reason": "ls_remote_failed", "err": res.get("err"), "out": res.get("out")}
    out = (res.get("out") or "").strip()
    return {"ok": bool(out), "reason": "exists" if out else "not_found"}


def _github_create_pr_via_api(*, title: str, body: str, head: str, base: str = "main") -> dict[str, Any]:
    token = _get_github_token()
    owner_repo = _get_origin_owner_repo()
    if not token:
        return {"ok": False, "reason": "missing_token"}
    if not owner_repo:
        return {"ok": False, "reason": "not_github_remote"}
    owner, repo = owner_repo
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    payload = json.dumps({"title": title, "body": body, "head": head, "base": base}).encode("utf-8")
    req = urllib.request.Request(url, method="POST")
    # GitHub accepts either "token" or "Bearer"; keep "token" for compatibility.
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        raw = urllib.request.urlopen(req, data=payload, timeout=30).read().decode("utf-8", errors="replace")
        pr_url: str | None = None
        try:
            obj = json.loads(raw)
            pr_url = obj.get("html_url")
        except Exception:
            # Fallback: best-effort regex for non-JSON responses
            m = re.search(r'"html_url"\s*:\s*"([^"]+)"', raw)
            pr_url = m.group(1) if m else None
        return {"ok": True, "pr_url": pr_url, "raw": raw[:2000]}
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(e)
        return {"ok": False, "reason": "http_error", "status": e.code, "detail": detail}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def _github_create_tools_pr_via_api(*, title: str, body: str, head: str, base: str = "main") -> dict[str, Any]:
    token = _get_github_token()
    owner_repo = _get_tools_origin_owner_repo()
    if not token:
        return {"ok": False, "reason": "missing_token"}
    if not owner_repo:
        return {"ok": False, "reason": "not_github_remote"}
    owner, repo = owner_repo
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    payload = json.dumps({"title": title, "body": body, "head": head, "base": base}).encode("utf-8")
    req = urllib.request.Request(url, method="POST")
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        raw = urllib.request.urlopen(req, data=payload, timeout=30).read().decode("utf-8", errors="replace")
        pr_url: str | None = None
        try:
            obj = json.loads(raw)
            pr_url = obj.get("html_url")
        except Exception:
            m = re.search(r'"html_url"\s*:\s*"([^"]+)"', raw)
            pr_url = m.group(1) if m else None
        return {"ok": True, "pr_url": pr_url, "raw": raw[:2000]}
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode("utf-8", errors="replace")
        except Exception:
            detail = str(e)
        return {"ok": False, "reason": "http_error", "status": e.code, "detail": detail}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def _github_compare_url(*, head: str, base: str = "main") -> str | None:
    owner_repo = _get_origin_owner_repo()
    if not owner_repo:
        return None
    owner, repo = owner_repo
    # "Compare & pull request" page. This works even without a token/gh.
    return f"https://github.com/{owner}/{repo}/compare/{base}...{head}?expand=1"


def _github_compare_url_tools(*, head: str, base: str = "main") -> str | None:
    owner_repo = _get_tools_origin_owner_repo()
    if not owner_repo:
        return None
    owner, repo = owner_repo
    return f"https://github.com/{owner}/{repo}/compare/{base}...{head}?expand=1"


def _notify_operational(tool_name: str, pr_url: str | None = None, request_id: int | None = None) -> str:
    parts = [f"Notify operational: tool={tool_name}"]
    if request_id is not None:
        parts.append(f"request_id={request_id}")
    if pr_url:
        parts.append(f"pr_url={pr_url}")
    return " | ".join(parts)


def run_developer_flow(
    tool_request_id: int,
    builder_agent_id: str,
    *,
    event_callback: Callable[[str, dict], None] | None = None,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    result: dict[str, Any] = {"ok": False, "request_id": tool_request_id, "steps": steps}

    def emit(step_name: str, payload: dict, msg: str | None = None) -> None:
        entry = {"step": step_name, "msg": msg, **payload}
        steps.append(entry)
        if event_callback:
            event_callback(step_name, payload)

    req = db.get_tool_request_by_id(tool_request_id)
    if not req:
        result["reason"] = "tool_request_not_found"
        emit("error", {"message": "Tool request not found"}, msg="Nie znaleziono requestu o podanym ID.")
        _tools_dbg(
            "H_BUILDER_REQ_NOT_FOUND",
            "tool request not found",
            {"tool_request_id": tool_request_id},
            run_id="builder_dbg",
            location="backend/agent_tools.py:run_developer_flow",
        )
        return result

    tool_name = (req.get("name") or "").strip()
    note = (req.get("note") or "").strip()
    _tools_dbg(
        "H_BUILDER_START",
        "run_developer_flow start",
        {"tool_request_id": tool_request_id, "tool_name": tool_name, "req_status": req.get("status"), "note_len": len(note)},
        run_id="builder_dbg",
        location="backend/agent_tools.py:run_developer_flow",
    )

    claim = db.claim_tool_request(tool_request_id, builder_agent_id)
    claim_ok = bool(claim.get("ok"))
    claim_reason = str(claim.get("reason") or "")
    if claim_ok:
        emit("reserve", {"claim_result": claim}, msg=f"Zarezerwowano request #{tool_request_id} ({tool_name}).")
    else:
        emit("reserve", {"claim_result": claim}, msg=f"Rezerwacja nieudana: {claim_reason or '?'}.")

    _tools_dbg(
        "H_BUILDER_CLAIM",
        "claim_tool_request result",
        {"claim_ok": claim_ok, "reason": claim_reason, "req_status_after?": None},
        run_id="builder_dbg",
        location="backend/agent_tools.py:run_developer_flow:claim",
    )

    if not claim_ok:
        result["reason"] = claim_reason or "claim_failed"
        return result

    query = f"{tool_name} {note}".strip() or tool_name
    sim = _find_similar_tools(query, threshold=SIMILARITY_THRESHOLD)
    if sim.get("matches"):
        best = sim["matches"][0]
        dup_name = best.get("name", "")
        db.register_tool_status(tool_request_id, status="duplicate", similarity_key=dup_name)
        emit("similarity_check", sim, msg="Znaleziono podobny tool – oznaczono jako duplikat.")
        emit("register_tool_status", {"status": "duplicate", "similarity_key": dup_name}, msg=f"Status: duplicate ({dup_name}).")
        emit("notify_operational", {"tool_name": tool_name, "duplicate": True}, msg="Powiadomiono operacyjnego o duplikacie.")
        _tools_dbg(
            "H_BUILDER_DUPLICATE",
            "similarity path: duplicate",
            {"duplicate_of": dup_name, "matches_count": len(sim.get("matches") or [])},
            run_id="builder_dbg",
            location="backend/agent_tools.py:run_developer_flow:duplicate",
        )
        result["ok"] = True
        result["duplicate_of"] = dup_name
        return result
    emit("similarity_check", sim, msg="No duplicates found — continuing with the implementation.")
    _tools_dbg(
        "H_BUILDER_NO_DUP",
        "no similarity duplicates",
        {"matches_count": len(sim.get("matches") or [])},
        run_id="builder_dbg",
        location="backend/agent_tools.py:run_developer_flow:no_dup",
    )

    # Provide implementation context so the steps UI shows clear guidance.
    builder_prompt = (
        "Tool implementation guidelines:\n"
        "- Canonical naming: snake_case, ASCII only.\n"
        "- Input: prefer a JSON-string payload (for example {users[], group, mode=add/remove}).\n"
        "- Validation: require required fields; if an identifier is missing, look it up by name/email before the operation.\n"
        "- Configuration: base URL + token/OAuth only from environment variables (never commit secrets).\n"
        "- Error handling: return a readable error with the HTTP code and a human description.\n"
        "- Output: return a deterministic JSON string (for example {ok, changed, skipped, errors}).\n"
    )
    emit("implementation_prompt", {"prompt": builder_prompt}, msg="Added tool implementation context.")

    branch_name = "tool/" + _to_tool_function_name(tool_name)
    if _git_is_tools_repo():
        # Checkout branch in Tools repo (source of truth for PRs).
        branch_res = _git(["checkout", "-b", branch_name], cwd=_TOOLS_REPO_ROOT)
        if not branch_res.get("ok"):
            branch_res = _git(["checkout", branch_name], cwd=_TOOLS_REPO_ROOT)
        emit("branch", branch_res, msg=f"Branch (tools repo): {branch_name}." if branch_res.get("ok") else f"Branch error: {branch_res.get('err') or branch_res.get('reason')}.")
    else:
        emit("branch", {"ok": False, "reason": "tools_repo_not_available", "tools_repo": str(_TOOLS_REPO_ROOT)}, msg="Brak repo Tools – pomijam branch/push/PR.")
    _tools_dbg(
        "H_BUILDER_REPO_CHECK",
        "tools repo availability + branch name",
        {
            "git_is_tools_repo": _git_is_tools_repo(),
            "branch_name": branch_name,
            "tools_repo_root_exists": str(_TOOLS_REPO_ROOT.exists()),
        },
        run_id="builder_dbg",
        location="backend/agent_tools.py:run_developer_flow:repo",
    )

    impl = _ensure_tool_in_operational_mcp(tool_name=tool_name, note=note)
    if not impl.get("ok"):
        db.register_tool_status(tool_request_id, status="failed")
        emit("implement_tool", {"result": impl}, msg="Tool implementation failed.")
        emit("register_tool_status", {"status": "failed"}, msg="Status ustawiony na: failed.")
        result["reason"] = impl.get("reason", "implement_failed")
        _tools_dbg(
            "H_BUILDER_IMPLEMENT_FAILED",
            "ensure tool in operational MCP failed",
            {"reason": str(impl.get("reason") or ""), "already_exists": bool(impl.get("already_exists"))},
            run_id="builder_dbg",
            location="backend/agent_tools.py:run_developer_flow:implement",
        )
        return result
    emit(
        "implement_tool",
        {"result": impl},
        msg=f"Added tool: {impl.get('func_name')}." if not impl.get("already_exists") else f"Tool {impl.get('func_name')} already existed — skipped.",
    )

    pr_url: str | None = None
    token_present = bool(_get_github_token())
    if _git_is_tools_repo():
        # Commit changes in Tools repo: tools/<tool>.py
        add_res = _git(["add", "tools"], cwd=_TOOLS_REPO_ROOT)
        emit("git_add", add_res, msg="git add (tools repo)")
        commit_res = _git(["commit", "-m", f"[Tool] {tool_name}"], cwd=_TOOLS_REPO_ROOT)
        # "nothing to commit" is not a fatal error for our flow
        commit_out = (commit_res.get("out") or "") + "\n" + (commit_res.get("err") or "")
        if (not commit_res.get("ok")) and ("nothing to commit" in commit_out.lower()):
            commit_res["ok"] = True
            commit_res["reason"] = "nothing_to_commit"
        emit(
            "git_commit",
            commit_res,
            msg="git commit"
            if commit_res.get("ok") and commit_res.get("reason") != "nothing_to_commit"
            else ("brak zmian do commita" if commit_res.get("reason") == "nothing_to_commit" else (commit_res.get("err") or "commit error")),
        )
        _tools_dbg(
            "H_BUILDER_GIT_COMMIT",
            "git add/commit summary",
            {"commit_ok": bool(commit_res.get("ok")), "commit_reason": str(commit_res.get("reason") or ""), "commit_code": commit_res.get("code")},
            run_id="builder_dbg",
            location="backend/agent_tools.py:run_developer_flow:commit",
        )
        # Prefer token push to avoid interactive auth prompts.
        # If token-based push fails (e.g. token scope/auth mismatch), retry via standard origin push.
        push_res = _git_push_with_token_tools(branch_name) if _get_github_token() else _git(["push", "-u", "origin", branch_name], cwd=_TOOLS_REPO_ROOT)
        if _get_github_token() and (not push_res.get("ok")):
            fallback_push = _git(["push", "-u", "origin", branch_name], cwd=_TOOLS_REPO_ROOT)
            emit(
                "git_push_fallback",
                fallback_push,
                msg="git push fallback (tools repo)" if fallback_push.get("ok") else (fallback_push.get("err") or "push fallback error"),
            )
            _tools_dbg(
                "H_BUILDER_GIT_PUSH_FALLBACK",
                "git push fallback result",
                {
                    "fallback_ok": bool(fallback_push.get("ok")),
                    "fallback_reason": str(fallback_push.get("reason") or ""),
                    "fallback_code": fallback_push.get("code"),
                },
                run_id="builder_dbg",
                location="backend/agent_tools.py:run_developer_flow:push_fallback",
            )
            if fallback_push.get("ok"):
                push_res = fallback_push
        emit("git_push", push_res, msg="git push (tools repo)" if push_res.get("ok") else (push_res.get("err") or "push error"))
        _tools_dbg(
            "H_BUILDER_GIT_PUSH",
            "git push result",
            {"push_ok": bool(push_res.get("ok")), "push_reason": str(push_res.get("reason") or ""), "push_code": push_res.get("code")},
            run_id="builder_dbg",
            location="backend/agent_tools.py:run_developer_flow:push",
        )
        if push_res.get("ok"):
            if _get_github_token():
                pr_res = _github_create_tools_pr_via_api(
                    title=f"[Tool] {tool_name}",
                    body=f"Implementation for tool request #{tool_request_id}.\n\n{note}".strip(),
                    head=branch_name,
                    base="main",
                )
                pr_url = pr_res.get("pr_url")
                emit(
                    "create_pr",
                    pr_res,
                    msg=(
                        f"PR: {pr_url}"
                        if pr_res.get("ok") and pr_url
                        else (
                            f"PR error: http {pr_res.get('status')}"
                            if (not pr_res.get("ok")) and pr_res.get("reason") == "http_error"
                            else (f"PR error: {pr_res.get('reason')}" if not pr_res.get("ok") else "PR utworzony, ale brak pr_url w odpowiedzi")
                        )
                    ),
                )
                _tools_dbg(
                    "H_BUILDER_PR_API",
                    "PR created via GitHub API",
                    {
                        "pr_api_ok": bool(pr_res.get("ok")),
                        "status_code": pr_res.get("status"),
                        "pr_url_present": bool(pr_url),
                        # Safe: no tokens/secrets; GitHub validation detail is non-sensitive.
                        "pr_detail_len": len(str(pr_res.get("detail") or "")),
                        "pr_detail_sample": str(pr_res.get("detail") or "")[:180],
                    },
                    run_id="builder_dbg",
                    location="backend/agent_tools.py:run_developer_flow:pr_api",
                )
                if not pr_url:
                    # If API failed (or returned no URL), keep UX unblocked with compare/new PR link.
                    fallback_pr_url = _github_compare_url_tools(head=branch_name, base="main")
                    if fallback_pr_url:
                        pr_url = fallback_pr_url
                        emit(
                            "create_pr_fallback",
                            {"ok": True, "reason": "compare_link_after_api_failure", "pr_url": pr_url, "head": branch_name, "base": "main"},
                            msg=f"PR fallback link (compare): {pr_url}",
                        )
                        _tools_dbg(
                            "H_BUILDER_PR_FALLBACK_AFTER_API",
                            "PR fallback compare link after API failure",
                            {"pr_api_ok": bool(pr_res.get('ok')), "pr_url_present_after_fallback": bool(pr_url)},
                            run_id="builder_dbg",
                            location="backend/agent_tools.py:run_developer_flow:pr_fallback_after_api",
                        )
            else:
                pr_url = _github_compare_url_tools(head=branch_name, base="main")
                emit(
                    "create_pr",
                    {"ok": True, "reason": "compare_link", "pr_url": pr_url, "head": branch_name, "base": "main"},
                    msg=f"PR link (compare): {pr_url}" if pr_url else "PR skipped (missing token) — could not resolve the GitHub Tools repo.",
                )
                _tools_dbg(
                    "H_BUILDER_PR_FALLBACK_COMPARE",
                    "PR fallback compare link (no token)",
                    {"token_present": token_present, "pr_url_present": bool(pr_url)},
                    run_id="builder_dbg",
                    location="backend/agent_tools.py:run_developer_flow:pr_fallback",
                )
        else:
            # Last-resort recovery: if branch already exists on origin, continue with PR creation flow.
            remote_branch = _git_remote_branch_exists_tools(branch_name)
            if remote_branch.get("ok"):
                _tools_dbg(
                    "H_BUILDER_GIT_PUSH_RECOVERY",
                    "push recovery: branch already exists on origin",
                    {"branch_name": branch_name, "recovered": True},
                    run_id="builder_dbg",
                    location="backend/agent_tools.py:run_developer_flow:push_recovery",
                )
                if _get_github_token():
                    pr_res = _github_create_tools_pr_via_api(
                        title=f"[Tool] {tool_name}",
                        body=f"Implementation for tool request #{tool_request_id}.\n\n{note}".strip(),
                        head=branch_name,
                        base="main",
                    )
                    pr_url = pr_res.get("pr_url") or _github_compare_url_tools(head=branch_name, base="main")
                    emit(
                        "create_pr_recovery",
                        {"ok": bool(pr_url), "reason": "push_failed_branch_exists_remote", "pr_url": pr_url},
                        msg=f"PR recovery: {pr_url}" if pr_url else "PR recovery failed.",
                    )
                else:
                    pr_url = _github_compare_url_tools(head=branch_name, base="main")
                    emit(
                        "create_pr_recovery",
                        {"ok": bool(pr_url), "reason": "push_failed_branch_exists_remote_no_token", "pr_url": pr_url},
                        msg=f"PR recovery: {pr_url}" if pr_url else "PR recovery failed.",
                    )
            else:
                emit("create_pr", {"ok": False, "reason": "push_failed"}, msg="PR skipped (push failed).")
            _tools_dbg(
                "H_BUILDER_PR_NOT_CREATED",
                "push failed so no PR",
                {"token_present": token_present, "branch_name": branch_name, "push_ok": bool(push_res.get("ok"))},
                run_id="builder_dbg",
                location="backend/agent_tools.py:run_developer_flow:pr_not_created",
            )
    else:
        _tools_dbg(
            "H_BUILDER_NO_TOOLS_REPO",
            "skip git/push/pr because tools repo unavailable",
            {"git_is_tools_repo": _git_is_tools_repo(), "branch_name": branch_name, "token_present": token_present},
            run_id="builder_dbg",
            location="backend/agent_tools.py:run_developer_flow:skip_tools_repo",
        )

    final_status = "pr_created" if pr_url else "ready_for_pr"
    reg = db.register_tool_status(
        tool_request_id,
        status=final_status,
        branch=branch_name,
        pr_url=pr_url,
        implemented_name=impl.get("func_name"),
    )
    emit("register_tool_status", {"status": final_status, "pr_url": pr_url, "db": reg}, msg=f"Zapisano status: {final_status}.")
    _tools_dbg(
        "H_BUILDER_FINAL_STATUS",
        "register_tool_status result",
        {"final_status": final_status, "pr_url_present": bool(pr_url), "implemented_name": impl.get("func_name")},
        run_id="builder_dbg",
        location="backend/agent_tools.py:run_developer_flow:final",
    )

    emit(
        "notify_operational",
        {"message": _notify_operational(tool_name, pr_url=pr_url, request_id=tool_request_id)},
        msg="Powiadomiono operacyjnego.",
    )

    result["ok"] = True
    result["pr_url"] = pr_url
    return result

