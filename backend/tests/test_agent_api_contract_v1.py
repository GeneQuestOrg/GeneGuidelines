from __future__ import annotations

import json
import unittest
from queue import Queue

from pydantic import ValidationError

from backend.routers import agent as agent_router
from backend.contracts.agent_api_v1 import (
    AGENT_API_CONTRACT_VERSION,
    AGENTIC_OUTPUT_CONTRACTS,
    PubmedArticle,
    PubmedEvidenceCard,
    PubmedRetrievalContract,
    build_agent_run_payload,
    get_agentic_output_contract,
    normalize_trace_event,
)


class AgentApiContractV1Tests(unittest.TestCase):
    def test_build_agent_run_payload_defaults_and_contract_version(self) -> None:
        payload = build_agent_run_payload({"execution_id": "x-1", "ticket_id": 123, "done": False})
        self.assertEqual(payload["contract_version"], AGENT_API_CONTRACT_VERSION)
        self.assertEqual(payload["execution_id"], "x-1")
        self.assertEqual(payload["ticket_id"], 123)
        self.assertEqual(payload["ai_summary"], {"issue": "", "work_log_summary": ""})
        self.assertEqual(payload["missing_tool_requests"], [])
        self.assertIsNone(payload["quality_snapshot"])
        self.assertIsNone(payload["current_stage"])

    def test_build_agent_run_payload_includes_current_stage(self) -> None:
        payload = build_agent_run_payload(
            {"execution_id": "x-2", "ticket_id": 1, "done": False, "last_stage": "node:pm-1:done"}
        )
        self.assertEqual(payload["current_stage"], "node:pm-1:done")

    def test_normalize_trace_event_sets_sys_kind_for_non_terminal_events(self) -> None:
        event = normalize_trace_event({"text": "hello"})
        self.assertEqual(event["kind"], "sys")

    def test_normalize_trace_event_keeps_done_event_without_kind(self) -> None:
        event = normalize_trace_event({"done": True})
        self.assertTrue(event["done"])
        self.assertNotIn("kind", event)

    def test_sse_trace_generator_normalizes_non_terminal_events(self) -> None:
        queue: Queue = Queue()
        queue.put({"text": "hello"})
        queue.put({"done": True})
        agent_router.TRACE_QUEUES["contract-test"] = queue
        try:
            generator = agent_router.sse_trace_generator("contract-test")
            payload = json.loads(next(generator).removeprefix("data: ").strip())
        finally:
            agent_router.TRACE_QUEUES.pop("contract-test", None)

        self.assertEqual(payload["kind"], "sys")
        self.assertEqual(payload["text"], "hello")

class PubmedRetrievalContractTests(unittest.TestCase):
    def test_minimal_valid_payload_round_trips_via_json(self) -> None:
        model = PubmedRetrievalContract(
            query_text="fibrous dysplasia",
            articles=[PubmedArticle(pmid="1", title="T", abstract="A")],
            evidence_cards=[PubmedEvidenceCard(pmid="1", topic_bucket="treatment")],
        )
        dumped = json.loads(model.model_dump_json())
        self.assertEqual(dumped["articles"][0]["pmid"], "1")
        self.assertEqual(dumped["evidence_cards"][0]["pmid"], "1")
        self.assertEqual(dumped["total_found_estimate"], 0)

    def test_article_without_pmid_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            PubmedArticle(pmid="", title="t")

    def test_unknown_topic_bucket_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            PubmedArticle(pmid="1", topic_bucket="bogus")

    def test_registry_maps_pm1_to_pubmed_contract(self) -> None:
        self.assertIs(get_agentic_output_contract("pm-1"), PubmedRetrievalContract)
        self.assertIs(AGENTIC_OUTPUT_CONTRACTS["pm-1"], PubmedRetrievalContract)
        self.assertIsNone(get_agentic_output_contract("unknown-node"))


if __name__ == "__main__":
    unittest.main()
