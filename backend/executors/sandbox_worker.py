"""
Sandbox worker for Code / Function node.

Contract:
- stdin: JSON object {"python_source": str, "context": Any}
- stdout: JSON object with execution result
"""
from __future__ import annotations

import ast
import io
import json
import os
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from typing import Any


MAX_RESULT_BYTES = int((os.environ.get("CODE_NODE_MAX_RESULT_BYTES") or "").strip() or 8_000_000)


def _json_error(message: str, error_type: str = "worker_error", details: str = "") -> dict[str, Any]:
    return {
        "ok": False,
        "error_type": error_type,
        "error": message,
        "details": details,
        "result": None,
        "stdout": "",
        "stderr": "",
    }


def _safe_import(name: str, globals_: dict | None = None, locals_: dict | None = None, fromlist=(), level: int = 0):
    allowed_modules = {"re", "json", "ipaddress", "urllib.parse", "datetime", "math"}
    if name not in allowed_modules:
        raise ImportError(f"Import '{name}' is not allowed in sandbox.")
    return __import__(name, globals_, locals_, fromlist, level)


def _safe_builtins() -> dict[str, Any]:
    # Minimal useful set for text/data transformations.
    # getattr/hasattr intentionally excluded — they allow class hierarchy traversal
    # and sandbox escape via ().__class__.__mro__[1].__subclasses__() etc.
    return {
        "__import__": _safe_import,
        "Exception": Exception,
        "print": print,
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "int": int,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "range": range,
        "reversed": reversed,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "type": type,
        "zip": zip,
    }


def _validate_source(source: str) -> None:
    tree = ast.parse(source, mode="exec")
    blocked_calls = {"eval", "exec", "compile", "open", "input", "__import__", "getattr", "hasattr", "setattr", "delattr"}

    for node in ast.walk(tree):
        if isinstance(node, (ast.With, ast.AsyncWith)):
            # File/network/resource context managers are risky in this MVP sandbox.
            raise ValueError("with/async with statements are not allowed in sandbox code.")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in blocked_calls:
                raise ValueError(f"Call to '{node.func.id}' is not allowed in sandbox code.")
        # Block dunder attribute access (e.g. obj.__class__, obj.__mro__) to prevent
        # class hierarchy traversal and sandbox escape.
        if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            raise ValueError(f"Access to dunder attribute '{node.attr}' is not allowed in sandbox code.")


def _to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(v) for v in value]
    return str(value)


def _trim_result(value: Any) -> Any:
    payload = _to_jsonable(value)
    raw = json.dumps(payload, ensure_ascii=False)
    if len(raw.encode("utf-8")) <= MAX_RESULT_BYTES:
        return payload
    return {
        "_truncated": True,
        "_reason": f"Result larger than {MAX_RESULT_BYTES} bytes",
        "preview": raw[:2000],
    }


def _run_user_code(source: str, context: Any) -> dict[str, Any]:
    _validate_source(source)

    globals_dict: dict[str, Any] = {"__builtins__": _safe_builtins()}
    locals_dict: dict[str, Any] = {}
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
        compiled = compile(source, "<sandbox_code>", "exec")
        exec(compiled, globals_dict, locals_dict)
        run_fn = locals_dict.get("run") or globals_dict.get("run")
        if not callable(run_fn):
            raise ValueError("Sandbox code must define callable function: run(context)")
        result = run_fn(context)

    return {
        "ok": True,
        "error_type": "",
        "error": "",
        "details": "",
        "result": _trim_result(result),
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
    }


def main() -> int:
    try:
        raw_in = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8").read()
        if not raw_in.strip():
            out = _json_error("No JSON payload on stdin.")
        else:
            payload = json.loads(raw_in)
            source = str(payload.get("python_source") or "")
            context = payload.get("context")
            if not source.strip():
                out = _json_error("Missing python_source in payload.")
            else:
                try:
                    out = _run_user_code(source, context)
                except Exception as exc:
                    out = _json_error(
                        message=str(exc),
                        error_type="execution_error",
                        details=traceback.format_exc(limit=8),
                    )
    except Exception as exc:  # pragma: no cover
        out = _json_error(str(exc), error_type="worker_crash", details=traceback.format_exc(limit=8))

    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
