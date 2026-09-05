"""docs/FLOWS.md stays in step with the flow specs.

Hand-drawn architecture docs go stale in a week, and a stale diagram is worse than
none — it teaches the wrong model of the system to whoever reads it next. The specs
are data the engine executes, so the picture is generated from them and this test
fails when the two drift.
"""

from __future__ import annotations

import pytest

from backend.scripts import render_flow_diagrams as rfd


def test_the_committed_diagram_matches_the_specs() -> None:
    """Change a flow, forget the diagram, this goes red.

    Fix by running: python3 -m backend.scripts.render_flow_diagrams
    """
    assert _OUT_TEXT() == rfd.render_all(), (
        "docs/FLOWS.md is stale — run `python3 -m backend.scripts.render_flow_diagrams`"
    )


def _OUT_TEXT() -> str:
    return rfd._OUT.read_text() if rfd._OUT.exists() else ""


@pytest.mark.parametrize("reserved", ["end", "class", "subgraph", "graph"])
def test_reserved_mermaid_words_never_become_node_ids(reserved: str) -> None:
    """Mermaid fails to render the WHOLE diagram on a reserved id, silently. Nearly
    every flow has a node called `end`, so this is not hypothetical."""
    assert rfd._safe(reserved) != reserved
    assert rfd._safe(reserved.upper()) != reserved.upper()


def test_hyphens_are_escaped_because_node_ids_use_them() -> None:
    assert "-" not in rfd._safe("gs-sec-diagnosis")


def test_every_node_and_edge_reaches_the_diagram() -> None:
    """A silently dropped node would make the picture a lie in the most damaging
    way: it would look complete."""
    import json

    for path in sorted(rfd._SPECS.glob("*.json")):
        spec = json.loads(path.read_text())
        rendered = rfd.render_flow(spec)
        for node in spec.get("nodes", []):
            assert rfd._safe(str(node["node_id"])) in rendered, (
                f"{path.name}: node {node['node_id']} missing from the diagram"
            )
        edges = [
            e
            for e in spec.get("edges", [])
            if e.get("source_node_id") and e.get("target_node_id")
        ]
        assert rendered.count(" --> ") + rendered.count(" -->|") == len(edges)


def test_domain_colouring_follows_the_executor_packages() -> None:
    assert rfd._domain_of("guideline_shelf_load") == "guidelines"
    assert rfd._domain_of("doctor_finder_step") == "doctors"
    assert rfd._domain_of("parent_pathway_load") == "pathways"
    assert rfd._domain_of("prompt") == "core"
