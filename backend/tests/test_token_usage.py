"""Token usage ledger and Pydantic AI usage recording."""
from __future__ import annotations

import threading

from pydantic_ai.usage import RunUsage

from backend.agents.token_usage import (
    RunTokenLedger,
    finalize_token_usage_for_store,
    ledger_for_store,
    record_from_pydantic_usage,
    snapshot_from_usage,
)


def test_snapshot_from_usage_none() -> None:
    snap = snapshot_from_usage(
        None,
        node_id="pm-2",
        model_spec="openai:gpt-4o-mini",
        prompt_mode="simple",
    )
    assert snap.input_tokens == 0
    assert snap.output_tokens == 0
    assert snap.usage_reported is False


def test_ledger_sums_two_snapshots() -> None:
    ledger = RunTokenLedger()
    ledger.record(
        snapshot_from_usage(
            RunUsage(input_tokens=100, output_tokens=50, requests=1),
            node_id="a",
            model_spec="openai:gpt-4o-mini",
            prompt_mode="simple",
        )
    )
    ledger.record(
        snapshot_from_usage(
            RunUsage(input_tokens=200, output_tokens=80, requests=2),
            node_id="b",
            model_spec="openai:gpt-4o-mini",
            prompt_mode="simple",
        )
    )
    totals = ledger.totals()
    assert totals["input_tokens"] == 300
    assert totals["output_tokens"] == 130
    assert totals["calls"] == 2
    assert ledger.by_node()["a"]["input_tokens"] == 100


def test_record_from_pydantic_usage_none_does_not_raise() -> None:
    ledger = RunTokenLedger()
    result = record_from_pydantic_usage(
        None,
        ledger=ledger,
        node_id="x",
        model_spec="openai:gpt-4o-mini",
        prompt_mode="simple",
        log_record=False,
    )
    assert result is not None
    assert result.usage_reported is False
    assert ledger.call_count == 1


def test_ledger_thread_safe() -> None:
    ledger = RunTokenLedger()
    usage = RunUsage(input_tokens=10, output_tokens=5, requests=1)

    def worker(idx: int) -> None:
        record_from_pydantic_usage(
            usage,
            ledger=ledger,
            node_id=f"n-{idx}",
            model_spec="openai:gpt-4o-mini",
            prompt_mode="simple",
            log_record=False,
        )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert ledger.call_count == 8
    assert ledger.totals()["input_tokens"] == 80


def test_to_store_payload_json_friendly() -> None:
    store: dict = {"execution_id": "exec-1"}
    ledger = ledger_for_store(store)
    record_from_pydantic_usage(
        RunUsage(input_tokens=1, output_tokens=2, requests=1),
        ledger=ledger,
        node_id="pm-1",
        model_spec="openai:gpt-4o-mini",
        prompt_mode="simple",
        log_record=False,
    )
    finalize_token_usage_for_store(store)
    payload = store["token_usage"]
    assert payload["total_tokens"] == 3
    assert payload["totals"]["input_tokens"] == 1
    assert len(payload["records"]) == 1
    assert "_token_ledger" in store
