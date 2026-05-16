from __future__ import annotations

import json
import logging
import re
from typing import Any

_logger = logging.getLogger(__name__)

_CONTEXT_REF = re.compile(
    r"""\{\{\s*context(?:\.([a-zA-Z0-9_.-]+)|\[['"]([^'"]+)['"]\]((?:\.[a-zA-Z0-9_-]+)*))\s*\}\}"""
)


def interpolate_context_placeholders(text: str, store: dict) -> str:
    """
    Replace {{ context.initial.field }} and {{ context.op-1.field }} from store['initial_context'] and store['node_outputs'].
    """
    if not text or "{{" not in text:
        return text
    initial = store.get("initial_context") or {}
    outputs = store.get("node_outputs") or {}
    memory = store.get("memory") or {}

    def _get(path: str) -> str:
        parts = path.split(".")
        if len(parts) < 2:
            return ""
        root, *rest = parts
        if root == "initial":
            cur: Any = initial
            for p in rest:
                if isinstance(cur, dict):
                    cur = cur.get(p)
                else:
                    return ""
            return "" if cur is None else str(cur)
        if root == "memory":
            cur: Any = memory
            for p in rest:
                if isinstance(cur, dict):
                    cur = cur.get(p)
                else:
                    return ""
            return "" if cur is None else str(cur)
        node_id = root
        blob = outputs.get(node_id)
        if not isinstance(blob, dict):
            _logger.debug("context placeholder unresolved: path=%r", path)
            return ""
        cur = blob
        for p in rest:
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                _logger.debug("context placeholder unresolved: path=%r", path)
                return ""
        return "" if cur is None else str(cur)

    def repl(m: re.Match) -> str:
        dot_path = m.group(1)
        if dot_path is not None:
            return _get(dot_path.strip())
        node_id = (m.group(2) or "").strip()
        rest = (m.group(3) or "").strip(".")
        path = ".".join(part for part in (node_id, rest) if part)
        return _get(path)

    return _CONTEXT_REF.sub(repl, text)


def interpolate_http_headers_json(headers_raw: str | None, store: dict) -> dict[str, str]:
    """
    Parse http_headers as JSON object; interpolate each string value with context placeholders.
    """
    raw = (headers_raw or "").strip()
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid http_headers JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError("http_headers must be a JSON object with string keys")
    out: dict[str, str] = {}
    for k, v in obj.items():
        key = str(k)
        if isinstance(v, (dict, list)):
            raise ValueError(f"http_headers value for {key!r} must be a string, not {type(v).__name__}")
        val = interpolate_context_placeholders(str(v), store)
        out[key] = val
    return out


def interpolate_body_recursive(store: dict, obj: Any) -> Any:
    """Recursively interpolate {{ context.* }} in string values of dict/list."""
    if isinstance(obj, dict):
        return {k: interpolate_body_recursive(store, v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [interpolate_body_recursive(store, item) for item in obj]
    if isinstance(obj, str):
        return interpolate_context_placeholders(obj, store)
    return obj
