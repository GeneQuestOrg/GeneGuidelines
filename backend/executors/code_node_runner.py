"""
Runner for sandboxed Python Code / Function nodes.

JSON contract:
- in:  {"python_source": str, "context": Any}
- out: {"ok": bool, "result": Any, "stdout": str, "stderr": str, "error": str, ...}
"""
from __future__ import annotations

import asyncio
import os
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from ..config import CODE_NODE_MAX_INPUT_BYTES, CODE_NODE_MAX_RESULT_BYTES, CODE_NODE_TIMEOUT_SEC

DEFAULT_TIMEOUT_SECONDS = CODE_NODE_TIMEOUT_SEC
DEFAULT_MAX_INPUT_BYTES = CODE_NODE_MAX_INPUT_BYTES
DEFAULT_MAX_LOG_BYTES = 24_000

def _truncate_text(text: str, max_bytes: int) -> tuple[str, bool]:
    data = (text or "").encode("utf-8", errors="replace")
    if len(data) <= max_bytes:
        return text or "", False
    cut = data[:max_bytes]
    return cut.decode("utf-8", errors="ignore"), True


def _emit(emit_fn, event_queue, payload: dict[str, Any]) -> None:
    if emit_fn is None or event_queue is None:
        return
    try:
        emit_fn(event_queue, payload)
    except Exception:
        # Emission failure should not fail execution.
        return


async def run_code_node_async(
    *,
    python_source: str,
    context: dict[str, Any] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES,
    max_log_bytes: int = DEFAULT_MAX_LOG_BYTES,
    node_id: str = "",
    event_queue=None,
    emit_fn=None,
) -> dict[str, Any]:
    """
    Execute code in subprocess sandbox worker and return normalized structured result.
    """
    payload = {
        "python_source": python_source or "",
        "context": context or {},
    }
    raw_in = json.dumps(payload, ensure_ascii=False)
    raw_in_bytes = raw_in.encode("utf-8")
    if len(raw_in_bytes) > max_input_bytes:
        return {
            "ok": False,
            "error": f"Sandbox input too large ({len(raw_in_bytes)} bytes > {max_input_bytes})",
            "error_type": "input_too_large",
            "timed_out": False,
            "duration_ms": 0,
            "exit_code": None,
            "result": None,
            "stdout_tail": "",
            "stderr_tail": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
        }

    worker_path = Path(__file__).resolve().parent / "sandbox_worker.py"
    cmd = [sys.executable, "-I", str(worker_path)]
    started = time.perf_counter()

    _emit(emit_fn, event_queue, {"kind": "code_node_start", "node_id": node_id})
    env = {
        "PYTHONIOENCODING": "utf-8",
        "CODE_NODE_MAX_RESULT_BYTES": str(CODE_NODE_MAX_RESULT_BYTES),
    }
    if os.name == "nt":
        sysroot = os.environ.get("SYSTEMROOT")
        if sysroot:
            env["SYSTEMROOT"] = sysroot
    with tempfile.TemporaryDirectory(prefix="gg_code_node_") as tmp_dir:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=tmp_dir,
            env=env,
        )

        timed_out = False
        stdout_b = b""
        stderr_b = b""
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(input=raw_in_bytes), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            stdout_b, stderr_b = await proc.communicate()
        except Exception:
            proc.kill()
            stdout_b, stderr_b = await proc.communicate()
            raise

        duration_ms = int((time.perf_counter() - started) * 1000)
    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    stdout_tail, stdout_truncated = _truncate_text(stdout, max_log_bytes)
    stderr_tail, stderr_truncated = _truncate_text(stderr, max_log_bytes)

    if timed_out:
        out = {
            "ok": False,
            "error": f"Sandbox timeout after {timeout_seconds:.2f}s",
            "error_type": "timeout",
            "timed_out": True,
            "duration_ms": duration_ms,
            "exit_code": proc.returncode,
            "result": None,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
        _emit(emit_fn, event_queue, {"kind": "code_node_error", "node_id": node_id, "error": out["error"]})
        return out

    parsed: dict[str, Any] | None = None
    parse_error = ""
    if stdout.strip():
        try:
            parsed = json.loads(stdout)
        except Exception as exc:
            parse_error = str(exc)

    if proc.returncode != 0:
        out = {
            "ok": False,
            "error": f"Sandbox worker exited with code {proc.returncode}",
            "error_type": "worker_non_zero_exit",
            "timed_out": False,
            "duration_ms": duration_ms,
            "exit_code": proc.returncode,
            "result": None,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
        _emit(emit_fn, event_queue, {"kind": "code_node_error", "node_id": node_id, "error": out["error"]})
        return out

    if parsed is None:
        out = {
            "ok": False,
            "error": f"Invalid JSON from sandbox worker: {parse_error or 'empty stdout'}",
            "error_type": "invalid_worker_json",
            "timed_out": False,
            "duration_ms": duration_ms,
            "exit_code": proc.returncode,
            "result": None,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
        _emit(emit_fn, event_queue, {"kind": "code_node_error", "node_id": node_id, "error": out["error"]})
        return out

    worker_stdout, worker_stdout_truncated = _truncate_text(str(parsed.get("stdout") or ""), max_log_bytes)
    worker_stderr, worker_stderr_truncated = _truncate_text(str(parsed.get("stderr") or ""), max_log_bytes)

    out = {
        "ok": bool(parsed.get("ok")),
        "error": str(parsed.get("error") or ""),
        "error_type": str(parsed.get("error_type") or ""),
        "details": str(parsed.get("details") or ""),
        "timed_out": False,
        "duration_ms": duration_ms,
        "exit_code": proc.returncode,
        "result": parsed.get("result"),
        "stdout_tail": worker_stdout,
        "stderr_tail": worker_stderr,
        "stdout_truncated": worker_stdout_truncated,
        "stderr_truncated": worker_stderr_truncated,
    }

    if out["ok"]:
        _emit(emit_fn, event_queue, {"kind": "code_node_result", "node_id": node_id, "ok": True})
    else:
        _emit(emit_fn, event_queue, {"kind": "code_node_error", "node_id": node_id, "error": out["error"]})
    return out
