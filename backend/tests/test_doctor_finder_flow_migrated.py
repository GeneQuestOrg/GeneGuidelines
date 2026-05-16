"""doctor_finder flow is added on startup for DBs seeded before that flow existed."""

from __future__ import annotations

from backend.database import _ensure_doctor_finder_flow, get_flow_definition_nodes


def test_ensure_doctor_finder_flow_idempotent() -> None:
    """After ensure, doctor_finder has expected nodes; second call does not duplicate."""
    _ensure_doctor_finder_flow()
    nodes = get_flow_definition_nodes("doctor_finder")
    assert len(nodes) >= 9
    ids = {str(n["node_id"]) for n in nodes}
    assert "start" in ids and "df-1" in ids and "df-7" in ids and "end" in ids
    _ensure_doctor_finder_flow()
    nodes2 = get_flow_definition_nodes("doctor_finder")
    assert len(nodes2) == len(nodes)
