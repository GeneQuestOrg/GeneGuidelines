"""Structured JSON logs for pipeline runs (grep-friendly in uvicorn stdout)."""
from __future__ import annotations

import json
import logging
from typing import Any

LOGGER = logging.getLogger("geneguidelines.run")
_RUN_LOGGER_CONFIGURED = False


def _ensure_run_logger_configured() -> None:
    global _RUN_LOGGER_CONFIGURED
    if _RUN_LOGGER_CONFIGURED:
        return
    LOGGER.setLevel(logging.INFO)
    if not LOGGER.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)
    LOGGER.propagate = False
    _RUN_LOGGER_CONFIGURED = True


def log_run_event(event: str, *, execution_id: str, **fields: Any) -> None:
    _ensure_run_logger_configured()
    payload: dict[str, Any] = {
        "logger": "geneguidelines.run",
        "event": event,
        "execution_id": execution_id,
    }
    for key, value in fields.items():
        if value is not None and value != "":
            payload[key] = value
    LOGGER.info(json.dumps(payload, ensure_ascii=False, default=str))


def record_run_stage(store: dict[str, Any], stage: str, *, event: str = "stage", **extra: Any) -> None:
    """Update in-memory stage, emit structured log, persist to guideline_run_results."""
    store["last_stage"] = stage
    store["current_stage"] = stage
    execution_id = str(store.get("execution_id") or "")
    if not execution_id:
        return
    fields: dict[str, Any] = {
        "stage": stage,
        "flow_key": store.get("flow_key"),
        "pipeline": store.get("pipeline"),
    }
    fields.update(extra)
    log_run_event(event, execution_id=execution_id, **fields)
    try:
        from ..guideline_run_store import update_guideline_run_stage
    except ImportError:
        from guideline_run_store import update_guideline_run_stage
    try:
        update_guideline_run_stage(execution_id, stage)
    except Exception:
        LOGGER.exception("Failed to persist run stage for %s", execution_id)


def log_llm_call(
    event: str,
    *,
    execution_id: str,
    node_id: str,
    **fields: Any,
) -> None:
    """Structured log for in-flight LLM calls (prompt size, timeout, duration)."""
    if not execution_id:
        return
    log_run_event(event, execution_id=execution_id, node_id=node_id, **fields)


def log_token_usage(event: str, *, execution_id: str, **fields: Any) -> None:
    """Structured log for aggregated or per-call LLM token usage."""
    if not execution_id:
        return
    log_run_event(event, execution_id=execution_id, **fields)


def summarize_node_output(node_out: Any) -> dict[str, Any]:
    """Compact node result for logs (no full LLM payloads)."""
    if not isinstance(node_out, dict):
        return {}
    summary: dict[str, Any] = {}
    if "ok" in node_out:
        summary["ok"] = node_out["ok"]
    if node_out.get("skipped"):
        summary["skipped"] = True
    err = node_out.get("error")
    if err:
        summary["error"] = str(err)[:200]
    result = node_out.get("result")
    if isinstance(result, dict):
        for key in (
            "total_analyzed",
            "total_found_estimate",
            "articles_text_corpus_capped",
            "retrieval_channel",
            "query_text",
        ):
            if key in result:
                summary[key] = result[key]
        articles = result.get("articles")
        if isinstance(articles, list):
            summary["article_count"] = len(articles)
    return summary
