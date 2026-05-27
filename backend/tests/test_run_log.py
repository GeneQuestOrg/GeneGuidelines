from __future__ import annotations

import json
import logging

from backend.observability.run_log import log_run_event, record_run_stage, summarize_node_output


def test_summarize_node_output_extracts_article_count() -> None:
    summary = summarize_node_output(
        {"ok": True, "result": {"articles": [{"pmid": "1"}], "total_analyzed": 1}}
    )
    assert summary["ok"] is True
    assert summary["article_count"] == 1
    assert summary["total_analyzed"] == 1


def test_log_run_event_emits_json(capsys) -> None:
    log_run_event("node_start", execution_id="exec-1", node_id="pm-1")
    payload = json.loads(capsys.readouterr().err.strip())
    assert payload["event"] == "node_start"
    assert payload["execution_id"] == "exec-1"
    assert payload["node_id"] == "pm-1"


def test_record_run_stage_updates_store(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def _fake_update(execution_id: str, stage: str) -> None:
        calls.append((execution_id, stage))

    monkeypatch.setattr(
        "backend.guideline_run_store.update_guideline_run_stage",
        _fake_update,
    )
    store: dict = {"execution_id": "exec-2", "flow_key": "pubmed", "pipeline": "guideline"}
    record_run_stage(store, "node:pm-2:running", event="node_start", node_id="pm-2")
    assert store["current_stage"] == "node:pm-2:running"
    assert calls == [("exec-2", "node:pm-2:running")]


def test_record_run_stage_allows_extra_flow_key_without_duplicate_kwarg() -> None:
    store: dict = {"execution_id": "exec-3", "flow_key": "pubmed", "pipeline": "guideline"}
    record_run_stage(store, "flow_fork:init", event="flow_fork_init", flow_key="pubmed")
    assert store["current_stage"] == "flow_fork:init"
