"""Sentry monitoring: off without a DSN, never sends query strings, and reports limits once per kind."""
from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from backend.shared import monitoring


def test_query_strings_are_stripped_from_every_url():
    text = "HTTPStatusError for url 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=Smith&api_key=abc123' and https://npiregistry.cms.hhs.gov/api/?first_name=Anna&state=CA."
    out = monitoring.strip_query_strings(text)
    assert "api_key" not in out and "abc123" not in out and "Anna" not in out
    assert "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?[filtered]" in out
    assert "https://npiregistry.cms.hhs.gov/api/?[filtered]" in out
    assert monitoring.strip_query_strings("no url here?") == "no url here?"


def test_passwords_in_connection_strings_are_stripped():
    text = 'missing "=" after "postgresql+psycopg://gg_admin:S3cr3t!x@gg-pg-prod.postgres.database.azure.com:5432/gg" in connection info string'
    out = monitoring.strip_query_strings(text)
    assert "S3cr3t" not in out
    assert "postgresql+psycopg://gg_admin:[filtered]@gg-pg-prod.postgres.database.azure.com:5432/gg" in out
    assert monitoring.strip_query_strings("postgresql://postgres@localhost:55432/gp_dev") == "postgresql://postgres@localhost:55432/gp_dev"


def test_scrub_reaches_nested_exception_values_and_leaves_other_types():
    event = {"exception": {"values": [{"type": "HTTPStatusError", "value": "GET https://clinicaltrials.gov/api/v2/studies?query.term=Kowalski failed"}]}, "level": "error", "count": 3, "tags": ("https://x.org/a?b=c",)}
    out = monitoring.scrub(event)
    assert out["exception"]["values"][0]["value"] == "GET https://clinicaltrials.gov/api/v2/studies?[filtered] failed"
    assert out["count"] == 3 and out["level"] == "error"
    assert out["tags"] == ["https://x.org/a?[filtered]"]
    assert "Kowalski" in event["exception"]["values"][0]["value"], "the original event is not changed in place"


def test_init_without_dsn_is_off(monkeypatch):
    monkeypatch.setattr(monitoring.config, "SENTRY_DSN", "")
    monkeypatch.setitem(monitoring._state, "enabled", False)
    assert monitoring.init_monitoring("api") is False
    assert monitoring._state["enabled"] is False


def test_report_limit_without_sentry_only_logs(monkeypatch, caplog):
    monkeypatch.setitem(monitoring._state, "enabled", False)
    with caplog.at_level(logging.WARNING, logger="backend.shared.monitoring"):
        monitoring.report_limit("input_budget", "documents left out", disease="fd", documents=2)
    assert "Limit hit: input_budget" in caplog.text


def test_report_limit_sends_one_warning_grouped_by_limit(monkeypatch):
    sent: list[tuple[str, dict]] = []
    counted: list[tuple] = []
    fake = SimpleNamespace(
        capture_message=lambda text, **kwargs: sent.append((text, kwargs)),
        metrics=SimpleNamespace(count=lambda *args, **kwargs: counted.append((args, kwargs))),
    )
    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", fake)
    monkeypatch.setitem(monitoring._state, "enabled", True)
    monitoring.report_limit("monthly_research_budget", "the run did not start", disease="mas", points=3)
    assert len(sent) == 1
    text, kwargs = sent[0]
    assert text.startswith("Limit hit: monthly_research_budget")
    assert kwargs["level"] == "warning"
    assert kwargs["fingerprint"] == ["limit", "monthly_research_budget"]
    assert kwargs["tags"] == {"limit": "monthly_research_budget", "disease": "mas", "points": "3"}
    assert counted == [(("limit.hit", 1), {"attributes": {"limit": "monthly_research_budget"}})]


def test_report_limit_never_raises_when_sentry_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setitem(__import__("sys").modules, "sentry_sdk", SimpleNamespace(capture_message=boom, metrics=SimpleNamespace(count=boom)))
    monkeypatch.setitem(monitoring._state, "enabled", True)
    monitoring.report_limit("model_refusal", "declined")


def test_points_service_reports_each_kind_of_limit_once(monkeypatch):
    from backend.guidelines.points import service
    from backend.guidelines.points.models import BlockRecord

    reports: list[tuple[str, dict]] = []
    monkeypatch.setattr(service, "report_limit", lambda limit, message, **tags: reports.append((limit, tags)))
    record = BlockRecord.from_loop({
        "calls": [{"step": "draft"}],
        "selection_notes": ["d1 (grade C) left out: input budget of 700000 characters reached", "d2 (grade C) left out: input budget of 700000 characters reached", "d3 (grade A) left out: no_pmcid"],
        "dropped": [
            {"why": "over the limit of 8 points"},
            {"why": "still failing after the last revision round"},
            {"why": "still failing after the last revision round"},
            {"why": "withdrawn by the generator: duplicate"},
        ],
    })
    service._report_limits("noonan", record)
    assert reports == [
        ("input_budget", {"component": "guideline_points", "disease": "noonan", "documents": 2}),
        ("max_points", {"component": "guideline_points", "disease": "noonan", "points": 1}),
        ("revision_rounds", {"component": "guideline_points", "disease": "noonan", "points": 2}),
    ]


@pytest.mark.parametrize(("stop_reason", "limit"), [("refusal", "model_refusal"), ("max_tokens", "model_output_cut")])
def test_claude_adapter_reports_refusals_and_cut_off_answers(monkeypatch, stop_reason, limit):
    from pydantic import BaseModel

    from backend.agents import anthropic_direct

    class Out(BaseModel):
        answer: str

    reports: list[str] = []
    monkeypatch.setattr(anthropic_direct, "report_limit", lambda name, message, **tags: reports.append(name))
    message = SimpleNamespace(stop_reason=stop_reason, usage=None, model="claude-sonnet-5-5", stop_details=None, content=[SimpleNamespace(type="text", text='{"answer": "cut')])
    with pytest.raises(anthropic_direct.ClaudeCallError):
        anthropic_direct.parse_message(message, Out)
    assert reports == [limit]
