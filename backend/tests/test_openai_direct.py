"""The direct OpenAI path used by the synthesis sections.

The synthesis is the one artefact a parent reads, so it runs on a frontier model
while everything else stays on the cheap one. Getting there needed a path around
pydantic-ai: reasoning models reject ``max_tokens`` in favour of
``max_completion_tokens``, and the pinned pydantic-ai (held back because mcp 2.0
broke the version above it) sends the former — so the model answered with nothing
and the node produced an empty section, silently.

These tests pin the two schema quirks that took three attempts to get past, and the
routing rule that keeps the expensive model on the synthesis only.
"""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, Field

from backend.agents import openai_direct


class _Inner(BaseModel):
    doc: str = Field(..., description="which document")


class _Outer(BaseModel):
    title: str = Field(default="", description="section title")
    source: _Inner = Field(..., description="provenance")


def test_strictify_marks_every_property_required() -> None:
    """OpenAI structured outputs demands it. Pydantic marks only non-defaulted
    fields required, so `title` (which has a default) would otherwise be omitted."""
    schema = openai_direct._strictify(_Outer.model_json_schema())

    assert set(schema["required"]) == {"title", "source"}
    assert schema["additionalProperties"] is False


def test_strictify_strips_keywords_that_sit_next_to_a_ref() -> None:
    """`$ref cannot have keywords {'description'}` — a hard 400 from the API.

    Pydantic emits `{"$ref": ..., "description": ...}` for a nested model field.
    """
    schema = openai_direct._strictify(_Outer.model_json_schema())
    source = schema["properties"]["source"]

    assert "$ref" in source
    assert list(source.keys()) == ["$ref"], "a $ref may carry nothing else"


def test_strictify_reaches_nested_definitions() -> None:
    schema = openai_direct._strictify(_Outer.model_json_schema())
    inner = schema["$defs"]["_Inner"]

    assert inner["additionalProperties"] is False
    assert inner["required"] == ["doc"]


def _fake_post(monkeypatch, *, status: int = 200, content: str = "", captured: dict | None = None):
    class _Resp:
        status_code = status
        text = content if status != 200 else ""

        def json(self):
            return {
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def post(self, url, json=None, headers=None):
            if captured is not None:
                captured["body"] = json
            return _Resp()

    monkeypatch.setattr(openai_direct.httpx, "Client", lambda **kw: _Client())


def test_it_sends_max_completion_tokens_not_max_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole reason this module exists."""
    captured: dict = {}
    _fake_post(monkeypatch, content=json.dumps({"title": "T", "source": {"doc": "X"}}), captured=captured)

    openai_direct.call_structured(
        model="gpt-6-astra", prompt="p", result_type=_Outer, api_key="k",
        max_completion_tokens=1234,
    )

    assert captured["body"]["max_completion_tokens"] == 1234
    assert "max_tokens" not in captured["body"]


def test_it_asks_for_a_strict_json_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}
    _fake_post(monkeypatch, content=json.dumps({"title": "T", "source": {"doc": "X"}}), captured=captured)

    openai_direct.call_structured(model="m", prompt="p", result_type=_Outer, api_key="k")

    fmt = captured["body"]["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True


def test_empty_content_returns_empty_rather_than_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    """A reasoning model that spends its budget thinking returns no content. That is
    a "raise the budget" signal, not a crash — and the caller turns it into a node
    error rather than writing an empty section."""
    _fake_post(monkeypatch, content="")

    assert openai_direct.call_structured(model="m", prompt="p", result_type=_Outer, api_key="k") == {}


def test_http_error_is_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_post(monkeypatch, status=400, content="bad request")

    with pytest.raises(RuntimeError, match="400"):
        openai_direct.call_structured(model="m", prompt="p", result_type=_Outer, api_key="k")


# --- routing ---------------------------------------------------------------


def test_only_the_synthesis_sections_use_the_expensive_model() -> None:
    """Cheap model for the thousands of triage calls, frontier model for the five
    calls a parent actually reads. Reversing that would be expensive and pointless.
    """
    import pathlib

    spec = json.loads(
        (pathlib.Path(__file__).resolve().parents[1] / "flows" / "specs" / "guideline_synthesis.json").read_text()
    )
    by_id = {n["node_id"]: n.get("model_name") for n in spec["nodes"]}

    for node_id, model in by_id.items():
        if node_id.startswith("gs-sec-"):
            assert model == "direct:gpt-6-astra", f"{node_id} must use the frontier model"
        else:
            assert model in (None, ""), f"{node_id} must inherit the active profile"


def test_direct_prefix_routes_around_pydantic_ai() -> None:
    from backend.agents.simple_runner import resolve_model_spec_for_node

    assert resolve_model_spec_for_node({"model_name": "direct:gpt-6-astra"}) == "direct:gpt-6-astra"


class _Sec(BaseModel):
    text: str


class _Out(BaseModel):
    sections: list[_Sec]


def _call_direct(monkeypatch, *, raises: Exception | None = None, key: str = "sk-test"):
    """Drive _run_direct_openai with the network stubbed out."""
    import asyncio
    from queue import Queue

    from backend.agents import openai_direct, simple_runner

    def _stub(**kwargs):
        if raises:
            raise raises
        _stub.seen = kwargs
        return {"sections": [{"text": "ok"}]}

    monkeypatch.setattr(openai_direct, "call_structured", _stub)
    monkeypatch.setenv("OPENAI_API_KEY", key)
    store: dict = {}
    result = asyncio.run(
        simple_runner._run_direct_openai(
            model="gpt-6-astra",
            system_prompt="s",
            user_prompt="u",
            result_type=_Out,
            max_tokens=300,
            store=store,
            event_queue=Queue(),
            node_id="gs-sec-diagnosis",
            emit_fn=lambda *_: None,
            poison_store_on_failure=True,
            sse_kind="llm",
        )
    )
    return result, store, getattr(_stub, "seen", None)


def test_the_direct_path_runs_end_to_end(monkeypatch) -> None:
    """Exercises the function body, which no import check can do.

    The FD re-synthesis died three times inside this one function: an import of a
    name backend.config does not define, then a leftover reference to that same name
    in the call itself, then a module logger that was never declared. Every one was a
    NameError raised only when the branch actually ran — on production, mid-run, with
    no content written and nothing red in CI.
    """
    result, store, seen = _call_direct(monkeypatch)

    assert store.get("error") is None
    assert result == {"sections": [{"text": "ok"}]}
    assert seen["api_key"] == "sk-test", "the key must reach the client"
    assert seen["max_completion_tokens"] >= 16_000, "reasoning models need headroom"


def test_a_failing_call_reports_through_the_store_not_a_second_exception(
    monkeypatch,
) -> None:
    """The except branch is where the undeclared logger hid — it only runs on failure,
    so a broken error path turns a recoverable failure into a NameError."""
    result, store, _ = _call_direct(monkeypatch, raises=RuntimeError("upstream 500"))

    assert result == {}
    assert "upstream 500" in str(store.get("error"))


def test_a_missing_key_fails_closed_with_a_readable_message(monkeypatch) -> None:
    result, store, _ = _call_direct(monkeypatch, key="")

    assert result == {}
    assert "OPENAI_API_KEY" in str(store.get("error"))
