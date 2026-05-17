"""JSON-defined workflow specs.

Each ``*.json`` file in this directory declares one workflow with its
nodes and edges. The shape is loaded at startup by
:func:`backend.database.ensure_flows_from_specs` and upserted into
``flow_definitions`` + ``flow_edges`` so the engine can execute it.

Schema (verified against the live ``flow_definitions`` columns):

.. code-block:: json

    {
      "flow_key": "official_guidelines_finder",
      "description": "Find the consensus paper for a disease",
      "nodes": [
        {
          "node_id": "start",
          "node_type": "trigger",
          "label": "Start",
          "description": "Entry point",
          "prompt": "",
          "prompt_mode": "agentic",
          "model_name": null,
          "loop_policy": "none",
          "execution_policy": "auto",
          "max_retry": 3,
          "output_schema": null,
          "output_schema_key": null,
          "python_source": null,
          "http_url": null,
          "http_method": null,
          "http_headers": null,
          "http_body": null
        }
      ],
      "edges": [
        {"source_node_id": "start", "target_node_id": "node_2"}
      ]
    }

Optional fields default to sane values; ``flow_key`` and ``node_id`` are
required for every node, ``source_node_id`` + ``target_node_id`` for every
edge.

The loader UPSERTs — running boot a second time updates any node whose
spec has changed and leaves data in ``guideline_run_results`` /
``doctor_finder_run_results`` untouched.
"""
