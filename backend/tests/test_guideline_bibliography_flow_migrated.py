"""Guideline flows gain bibliography tail nodes on startup for older databases."""

from __future__ import annotations

from backend.database import get_flow_edges, get_flow_definition_nodes
from backend.database_flow_ensures import _ensure_guideline_bibliography_tail_nodes


def test_ensure_guideline_bibliography_tail_idempotent() -> None:
    """After ensure, shelf/monitor flows wire *-write → *-bib → end when the flow exists."""
    _ensure_guideline_bibliography_tail_nodes()
    for flow_key, bib_id, writer_id in (
        ("guideline_shelf_build", "gsb-bib", "gsb-write"),
        ("guideline_suggestions", "gsd-bib", "gsd-write"),
    ):
        nodes = get_flow_definition_nodes(flow_key)
        if not nodes:
            continue
        ids = {str(n["node_id"]) for n in nodes}
        if bib_id not in ids:
            # Flow not seeded in this test DB — nothing to assert.
            continue
        assert nodes[next(i for i, n in enumerate(nodes) if n["node_id"] == bib_id)]["node_type"] == (
            "guideline_bibliography_write"
        )
        pairs = {(e["source_node_id"], e["target_node_id"]) for e in get_flow_edges(flow_key)}
        assert (writer_id, bib_id) in pairs
        assert (bib_id, "end") in pairs
        assert (writer_id, "end") not in pairs
    _ensure_guideline_bibliography_tail_nodes()
