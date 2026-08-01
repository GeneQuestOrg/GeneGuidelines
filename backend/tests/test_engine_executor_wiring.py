"""Every registered executor must be reachable from the flow engine.

The engine dispatches to ``EXECUTOR_REGISTRY`` only for node types listed in
hardcoded tuples (one guard + one dispatch list, duplicated across the
sequential and the parallel/fork path). Registering an executor without adding
its node type to those lists does not fail loudly: the engine treats the node
as unknown, writes ``{}`` into ``node_outputs`` and moves on, so every
downstream ``{{ context.<node>.* }}`` placeholder silently renders empty.

That is exactly how Feature 4 shipped inert — ``guideline_quote_extract_load``
was in the registry, the flow, and the tests, but never in the engine lists, so
the quote prompt ran with no claims and returned an empty list on every run.
"""

from __future__ import annotations

from pathlib import Path

from backend.executors import EXECUTOR_REGISTRY

_ENGINE_SOURCE = Path(__file__).resolve().parents[1] / "engine" / "flow_engine.py"

# Registry entries the engine reaches under a different node_type string:
# ``agentic_prompt`` is served by the ``prompt`` branch (prompt_mode="agentic")
# and ``http`` by the ``http_request`` branch. Both are legacy aliases, not
# node types a flow spec dispatches on.
_ENGINE_ALIASES = {"agentic_prompt", "http"}


def test_every_registered_executor_is_wired_into_the_engine() -> None:
    source = _ENGINE_SOURCE.read_text(encoding="utf-8")
    missing = [
        node_type
        for node_type in EXECUTOR_REGISTRY
        if node_type not in _ENGINE_ALIASES and f'"{node_type}"' not in source
    ]
    assert not missing, (
        "node types registered in EXECUTOR_REGISTRY but absent from "
        f"flow_engine.py dispatch lists: {missing}. The engine will skip these "
        "nodes silently and leave their context entry empty."
    )
