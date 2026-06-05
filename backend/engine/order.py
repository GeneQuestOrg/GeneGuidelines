from __future__ import annotations

import re

from .. import database as db


def get_execution_order(flow_key: str) -> list[str]:
    """
    Return ordered list of node_ids (topological order, supports fan-in).
    Uses flow_edges and Kahn's algorithm; assumes graph is a DAG (no cycles).
    """
    nodes = db.get_flow_definition_nodes(flow_key)
    edges = db.get_flow_edges(flow_key)
    if not nodes:
        return []

    def _sort_key(nid: str) -> tuple[str, int]:
        # node ids like "op-2", "bl-10" (numeric suffix)
        m = re.match(r"^([a-zA-Z]+)-(\d+)$", nid)
        if m:
            return (m.group(1), int(m.group(2)))
        return ("", 0)

    node_ids = sorted((n["node_id"] for n in nodes), key=_sort_key)
    indegree: dict[str, int] = {nid: 0 for nid in node_ids}
    outgoing: dict[str, list[str]] = {nid: [] for nid in node_ids}

    for e in edges:
        src = e["source_node_id"]
        tgt = e["target_node_id"]
        if src not in indegree:
            indegree[src] = 0
            outgoing.setdefault(src, [])
        if tgt not in indegree:
            indegree[tgt] = 0
            outgoing.setdefault(tgt, [])
        outgoing[src].append(tgt)
        indegree[tgt] += 1

    for src in outgoing:
        outgoing[src] = sorted(outgoing[src], key=_sort_key)

    ready = sorted([nid for nid in indegree if indegree[nid] == 0], key=_sort_key)
    order: list[str] = []

    while ready:
        nid = ready.pop(0)
        order.append(nid)
        for tgt in outgoing.get(nid, []):
            indegree[tgt] -= 1
            if indegree[tgt] == 0:
                ready.append(tgt)
        ready = sorted(ready, key=_sort_key)  # keep deterministic

    # Cycle guard: if graph has cycles, fall back to node order to avoid deadlock.
    if len(order) != len(indegree):
        return sorted(indegree.keys(), key=_sort_key)

    # Only return nodes that are part of flow_definitions.
    flow_node_set = {n["node_id"] for n in nodes}
    filtered = [nid for nid in order if nid in flow_node_set]
    return filtered
