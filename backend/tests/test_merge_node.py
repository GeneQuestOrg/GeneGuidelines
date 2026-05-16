from __future__ import annotations

import unittest
from unittest.mock import patch

from backend.engine.flow_engine import get_execution_order, merge_values


class MergeNodeValueTests(unittest.TestCase):
    def test_append_ok(self) -> None:
        out = merge_values(
            strategy="append",
            fields=["items"],
            source_outputs=[{"items": [1, 2]}, {"items": [3, 4]}],
            merge_key_field="id",
        )
        self.assertEqual(out, {"items": [1, 2, 3, 4]})

    def test_zip_ok(self) -> None:
        out = merge_values(
            strategy="zip",
            fields=["items"],
            source_outputs=[{"items": [1, 2]}, {"items": ["a", "b"]}],
            merge_key_field="id",
        )
        self.assertEqual(out, {"items": [[1, "a"], [2, "b"]]})

    def test_zip_error_length_mismatch(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            merge_values(
                strategy="zip",
                fields=["items"],
                source_outputs=[{"items": [1, 2]}, {"items": ["a"]}],
                merge_key_field="id",
            )
        self.assertIn("zip_error", str(ctx.exception))

    def test_combine_by_key_ok(self) -> None:
        out = merge_values(
            strategy="combine_by_key",
            fields=["rows"],
            source_outputs=[
                {"rows": [{"id": 1, "a": 1}]},
                {"rows": [{"id": 1, "b": 2}, {"id": 2, "a": 3}]},
            ],
            merge_key_field="id",
        )
        self.assertEqual(
            out,
            {
                "rows": [
                    {"id": 1, "a": 1, "b": 2},
                    {"id": 2, "a": 3},
                ]
            },
        )

    def test_combine_by_key_conflict(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            merge_values(
                strategy="combine_by_key",
                fields=["rows"],
                source_outputs=[
                    {"rows": [{"id": 1, "a": 1}]},
                    {"rows": [{"id": 1, "a": 99}]},
                ],
                merge_key_field="id",
            )
        self.assertIn("zip_error", str(ctx.exception))


class MergeNodeSchedulerTests(unittest.TestCase):
    def test_topological_order_merges_after_predecessors(self) -> None:
        nodes = [
            {"node_id": "start"},
            {"node_id": "a"},
            {"node_id": "b"},
            {"node_id": "m"},
            {"node_id": "end"},
        ]
        edges = [
            {"source_node_id": "start", "target_node_id": "a"},
            {"source_node_id": "start", "target_node_id": "b"},
            {"source_node_id": "a", "target_node_id": "m"},
            {"source_node_id": "b", "target_node_id": "m"},
            {"source_node_id": "m", "target_node_id": "end"},
        ]

        with patch("backend.engine.flow_engine.db.get_flow_definition_nodes", return_value=nodes), patch(
            "backend.engine.flow_engine.db.get_flow_edges", return_value=edges
        ):
            order = get_execution_order("test-flow")

        self.assertLess(order.index("a"), order.index("m"))
        self.assertLess(order.index("b"), order.index("m"))
        self.assertLess(order.index("m"), order.index("end"))


if __name__ == "__main__":
    unittest.main()

