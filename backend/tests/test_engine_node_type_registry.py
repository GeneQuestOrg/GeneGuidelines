"""Registering an executor is enough to make its node type runnable.

The engine used to gate node types on a tuple typed out by hand, repeated in the
file. A node type absent from that tuple was skipped SILENTLY — no error, no failed
run, the node simply produced nothing. Feature 4 (per-claim source paraphrases)
shipped that way and sat inert on production until a parent read the page and asked
why the guideline had no quotes.

That failure mode is the reason for domain isolation in the first place: adding a
node to the guideline flow could do nothing, or a change elsewhere could quietly
drop a node type the doctor flow depends on, and nothing anywhere would go red.
"""

from __future__ import annotations

from backend.engine.flow_engine import _ENGINE_NATIVE_NODE_TYPES, _supported_node_types
from backend.executors import EXECUTOR_REGISTRY


def test_every_registered_executor_is_runnable() -> None:
    """The whole point: register an executor, the engine runs it. No second list."""
    supported = _supported_node_types()

    missing = sorted(set(EXECUTOR_REGISTRY) - supported)
    assert not missing, (
        f"these node types have an executor but the engine will skip them: {missing}"
    )


def test_control_flow_types_the_engine_implements_itself_are_supported() -> None:
    """`loop`, `end` and friends have no executor — the engine handles them inline —
    so they have to be named somewhere. This is the only hand-written list left."""
    supported = _supported_node_types()

    for native in ("loop", "end", "action", "http_request"):
        assert native in supported


def test_an_unregistered_node_type_is_not_silently_supported() -> None:
    assert "totally_made_up_node" not in _supported_node_types()


def test_the_hand_written_list_stays_small() -> None:
    """If this grows, node types are creeping back into the engine instead of the
    registry, and the silent-skip failure mode comes back with them."""
    assert len(_ENGINE_NATIVE_NODE_TYPES) <= 6


def test_node_types_used_by_shipped_flows_are_all_runnable() -> None:
    """End-to-end guard across domains: guidelines, doctors and pathways alike.

    A flow spec naming a node type nothing can run is a flow that does nothing at
    that step — the exact defect this file exists to prevent, caught here for every
    flow we ship rather than one at a time.
    """
    import json
    import pathlib

    specs = (pathlib.Path(__file__).resolve().parents[1] / "flows" / "specs").glob("*.json")
    supported = _supported_node_types()

    unrunnable: dict[str, set[str]] = {}
    for spec_path in specs:
        spec = json.loads(spec_path.read_text())
        for node in spec.get("nodes", []):
            node_type = str(node.get("node_type") or "").strip().lower()
            # "trigger" is a start marker, never executed.
            if node_type and node_type != "trigger" and node_type not in supported:
                unrunnable.setdefault(spec_path.name, set()).add(node_type)

    assert not unrunnable, f"flow specs name node types nothing can run: {unrunnable}"
