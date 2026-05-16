"""
HTTP Request node executor: one outbound REST call with timeout and response size limit.
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ..config import HTTP_REQUEST_TIMEOUT_SEC
from ..security.http_url import validate_public_http_url

DEFAULT_TIMEOUT_SECONDS = HTTP_REQUEST_TIMEOUT_SEC
MAX_RESPONSE_BYTES = 1_048_576  # 1 MiB

ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})


def _emit(emit_fn, event_queue, payload: dict[str, Any]) -> None:
    if emit_fn is None or event_queue is None:
        return
    try:
        emit_fn(event_queue, payload)
    except Exception:
        return


async def run_http_request_async(
    *,
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
    node_id: str = "",
    event_queue=None,
    emit_fn=None,
) -> dict[str, Any]:
    """
    Perform HTTP request; return dict stored in node_outputs[node_id].
    """
    started = time.perf_counter()
    url_err = validate_public_http_url(url)
    if url_err:
        return {
            "ok": False,
            "error": url_err,
            "error_type": "invalid_url",
            "status_code": None,
            "body": None,
            "response_headers": {},
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }

    m = (method or "GET").strip().upper()
    if m not in ALLOWED_METHODS:
        return {
            "ok": False,
            "error": f"Unsupported HTTP method: {method!r} (allowed: {', '.join(sorted(ALLOWED_METHODS))})",
            "error_type": "invalid_method",
            "status_code": None,
            "body": None,
            "response_headers": {},
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }

    hdrs = dict(headers or {})
    request_kwargs: dict[str, Any] = {"method": m, "url": url, "headers": hdrs}
    if m in ("POST", "PUT", "PATCH") and body is not None and str(body).strip():
        request_kwargs["content"] = body.encode("utf-8") if isinstance(body, str) else body

    _emit(emit_fn, event_queue, {"kind": "http_request_start", "node_id": node_id, "method": m})

    timeout = httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds))
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            async with client.stream(**request_kwargs) as resp:
                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > max_response_bytes:
                        out = {
                            "ok": False,
                            "error": f"Response body larger than {max_response_bytes} bytes",
                            "error_type": "response_too_large",
                            "status_code": resp.status_code,
                            "body": None,
                            "response_headers": {k: str(v) for k, v in resp.headers.items()},
                            "duration_ms": int((time.perf_counter() - started) * 1000),
                        }
                        _emit(emit_fn, event_queue, {"kind": "http_request_error", "node_id": node_id, "error": out["error"]})
                        return out
                    chunks.append(chunk)
                raw = b"".join(chunks)
                status = resp.status_code
                resp_hdrs = {k: str(v) for k, v in resp.headers.items()}
    except httpx.TimeoutException as e:
        out = {
            "ok": False,
            "error": f"HTTP timeout after {timeout_seconds:.1f}s: {e}",
            "error_type": "timeout",
            "status_code": None,
            "body": None,
            "response_headers": {},
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
        _emit(emit_fn, event_queue, {"kind": "http_request_error", "node_id": node_id, "error": out["error"]})
        return out
    except httpx.RequestError as e:
        out = {
            "ok": False,
            "error": str(e),
            "error_type": "request_error",
            "status_code": None,
            "body": None,
            "response_headers": {},
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
        _emit(emit_fn, event_queue, {"kind": "http_request_error", "node_id": node_id, "error": out["error"]})
        return out

    duration_ms = int((time.perf_counter() - started) * 1000)
    ct = (resp_hdrs.get("content-type") or "").lower()
    body_out: Any
    try:
        text = raw.decode("utf-8")
        if "application/json" in ct or (text.strip().startswith("{") and text.strip().endswith("}")):
            try:
                body_out = json.loads(text)
            except json.JSONDecodeError:
                body_out = text
        else:
            body_out = text
    except UnicodeDecodeError:
        body_out = raw.decode("utf-8", errors="replace")

    ok = 200 <= status < 300
    out = {
        "ok": ok,
        "error": "" if ok else f"HTTP {status}",
        "error_type": "" if ok else "http_status",
        "status_code": status,
        "body": body_out,
        "response_headers": resp_hdrs,
        "duration_ms": duration_ms,
    }
    if ok:
        _emit(emit_fn, event_queue, {"kind": "http_request_result", "node_id": node_id, "status_code": status})
    else:
        _emit(emit_fn, event_queue, {"kind": "http_request_error", "node_id": node_id, "error": out["error"]})
    return out
