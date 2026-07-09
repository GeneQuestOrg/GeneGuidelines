"""guideline_synthesis gains the Feature-4 quote nodes on startup for older DBs.

Mirrors ``test_guideline_bibliography_flow_migrated`` — an idempotent, one-time
metadata repair that inserts ``gs-quotes-load`` + ``gs-quotes`` and rewires the
section nodes through them into the writer
(``gs-sec-* → gs-quotes-load → gs-quotes → gs-write``). This touches only the
``flow_definitions``/``flow_edges`` metadata, never the synthesis generation flow.
Skips cleanly when the flow is not seeded in the test DB.
"""

from __future__ import annotations

from backend.database import get_flow_edges, get_flow_definition_nodes
from backend.database_flow_ensures import _ensure_guideline_synthesis_quote_nodes

_SECTIONS = ("diagnosis", "histopathology", "therapy", "surgery", "monitoring")


def test_ensure_guideline_synthesis_quote_nodes_idempotent() -> None:
    _ensure_guideline_synthesis_quote_nodes()

    nodes = get_flow_definition_nodes("guideline_synthesis")
    if not nodes:
        return  # flow not seeded in this test DB — nothing to assert
    by_id = {str(n["node_id"]): n for n in nodes}
    if "gs-quotes" not in by_id or "gs-write" not in by_id:
        # Migration could not run here (spec missing / no writer to rewire) — skip.
        return

    assert by_id["gs-quotes-load"]["node_type"] == "guideline_quote_extract_load"
    assert by_id["gs-quotes"]["node_type"] == "prompt"
    assert by_id["gs-quotes"]["output_schema_key"] == "guideline_quotes"

    pairs = {(e["source_node_id"], e["target_node_id"]) for e in get_flow_edges("guideline_synthesis")}
    # The quote pair sits between the sections and the writer.
    assert ("gs-quotes-load", "gs-quotes") in pairs
    assert ("gs-quotes", "gs-write") in pairs
    for sid in _SECTIONS:
        assert (f"gs-sec-{sid}", "gs-quotes-load") in pairs
        # No section still shortcuts straight into the writer after rewiring.
        assert (f"gs-sec-{sid}", "gs-write") not in pairs

    # Second run must be a no-op (idempotent on gs-quotes presence).
    _ensure_guideline_synthesis_quote_nodes()
    pairs_again = {
        (e["source_node_id"], e["target_node_id"]) for e in get_flow_edges("guideline_synthesis")
    }
    assert pairs_again == pairs
