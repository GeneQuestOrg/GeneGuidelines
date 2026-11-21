"""Task 4: the disease "wider search" (generator, then judge) on 30 known-answer queries.

The product's own ``identify_disease_wider`` runs unchanged: its query interpretation, prompts, schemas, judge hand-off, normalisation and degradation when a stage fails. Only the function that calls a model is swapped, per stage, for the arm's caller. The product's 45-second per-stage timeout applies to every arm.
"""

from __future__ import annotations

import time
from typing import Any

from .common import mean, median

TASK = "search"
GEN_SPEC = "experiment:generator"
JUDGE_SPEC = "experiment:judge"


def units(snapshot: dict) -> list[dict]:
    return [{"unit": c["id"], **c} for c in snapshot["cases"]]


class SearchProductCaller:
    """The shipped path for one stage: the product's run_structured_with_ollama_fallback with a real model spec."""

    provider = "product-runner"

    def __init__(self, model_spec: str, original) -> None:
        self.model = model_spec
        self.effort = None
        self._original = original

    @property
    def label(self) -> str:
        return self.model

    async def structured(self, *, system, user, result_type, product_max_tokens, max_retry=1, unit="", cache=False, timeout_sec=None) -> dict[str, Any]:
        from .callers import _record, classify_error_text

        rec = _record(self.provider, self.model, system=system, user=user, result_type=result_type, max_tokens=product_max_tokens, effort=None, unit=unit)
        started = time.monotonic()
        try:
            out, spec, usage = await self._original(system_prompt=system, user_prompt=user, result_type=result_type, primary_spec=self.model, max_tokens=product_max_tokens, timeout_sec=timeout_sec, return_usage=True)
            rec.update({"ok": True, "output": out.model_dump(), "stop_reason": "end_turn", "usage": {"input_tokens": usage[0], "output_tokens": usage[1]}, "model_used": spec})
        except Exception as exc:  # noqa: BLE001 - the product degrades on any stage failure; the record keeps why
            message = f"{type(exc).__name__}: {exc}"
            rec["error"] = {"type": type(exc).__name__, "kind": "timeout" if "Timeout" in type(exc).__name__ else classify_error_text(message), "message": message[:400]}
        rec["latency_ms"] = round((time.monotonic() - started) * 1000)
        rec["attempts"] = [{"ok": rec["ok"], "error": (rec["error"] or {}).get("kind")}]
        rec["first_attempt_ok"] = rec["ok"]
        return rec


async def run_case(case: dict, generator, judge) -> dict[str, Any]:
    """One query through the product's pipeline with the arm's callers; ``judge`` None reproduces the product without a judge."""
    from backend import config
    from backend.services import disease_wider_search as wider

    from .common import LabError

    calls: list[dict] = []
    stopped: list[LabError] = []

    async def swapped(*, system_prompt, user_prompt, result_type, primary_spec, max_tokens, timeout_sec=None, return_usage=False):
        caller = generator if primary_spec == GEN_SPEC else judge
        stage = "generator" if primary_spec == GEN_SPEC else "judge"
        try:
            rec = await caller.structured(system=system_prompt, user=user_prompt, result_type=result_type, product_max_tokens=max_tokens, unit=f"{case['id']}:{stage}", timeout_sec=timeout_sec)
        except LabError as exc:
            # The product swallows stage failures; a budget stop must not be recorded as a model failure.
            stopped.append(exc)
            raise
        rec["stage"] = stage
        calls.append(rec)
        if not rec["ok"]:
            raise RuntimeError(f"{stage} failed: {(rec.get('error') or {}).get('kind')}")
        return result_type.model_validate(rec["output"]), primary_spec

    saved = (wider.run_structured_with_ollama_fallback, wider.resolve_gemma_or_fallback_spec, config.WIDER_SEARCH_JUDGE_MODEL)
    wider.run_structured_with_ollama_fallback = swapped
    wider.resolve_gemma_or_fallback_spec = lambda: GEN_SPEC
    config.WIDER_SEARCH_JUDGE_MODEL = JUDGE_SPEC if judge is not None else None
    started = time.monotonic()
    try:
        result = await wider.identify_disease_wider(case["query"])
    finally:
        wider.run_structured_with_ollama_fallback, wider.resolve_gemma_or_fallback_spec, config.WIDER_SEARCH_JUDGE_MODEL = saved
    if stopped:
        raise stopped[0]
    output = result.model_dump()
    return {"output": output, "calls": calls, "latency_ms": round((time.monotonic() - started) * 1000), "error": None if calls and calls[0]["ok"] else {"kind": "generator_failed"}}


def stub_output(result_type, unit: str, user: str) -> dict:
    name = result_type.__name__
    if name == "_GeneratorDraft":
        return {"interpreted_as": "stub", "candidates": [{"canonical_name": "Fibrous dysplasia", "gene": "GNAS", "omim": "174800", "inheritance": "", "category": "genetic", "summary": "stub", "evidence": "stub", "confidence": 0.9}], "notes": "stub"}
    return {"identified": True, "candidates": [{"canonical_name": "Fibrous dysplasia", "gene": "GNAS", "omim": "174800", "inheritance": "", "category": "genetic", "summary": "stub", "evidence": "stub", "verdict": "confirmed", "confidence": 0.9}], "verdict_note": "stub"}


# --- scoring ---------------------------------------------------------------------------------------------------------------

def _norm(text: str) -> str:
    return " ".join((text or "").lower().replace("’", "'").split())


def candidate_correct(candidate: dict, case: dict) -> bool:
    expect = case["expect"]
    name = _norm(candidate.get("canonical_name"))
    if any(_norm(a) in name for a in expect.get("accept_names") or []):
        return True
    genes = {g.upper() for g in expect.get("accept_genes") or []}
    return case["kind"] in ("gene", "identifier") and bool(genes) and (candidate.get("gene") or "").strip().upper() in genes


def score_trial(case: dict, trial: dict) -> dict:
    expect = case["expect"]
    candidates = (trial.get("output") or {}).get("candidates") or []
    abstained = not candidates
    names = [_norm(c.get("canonical_name")) for c in candidates]
    must_not_hit = any(_norm(bad) in n for bad in expect.get("must_not") or [] for n in names)
    top_ok = bool(candidates) and candidate_correct(candidates[0], case)
    any_ok = any(candidate_correct(c, case) for c in candidates)
    if expect.get("must_abstain"):
        passed = abstained
    elif abstained:
        passed = bool(expect.get("abstain_ok"))
    else:
        passed = top_ok and not must_not_hit
    wrong_answer = not abstained and (must_not_hit or bool(expect.get("must_abstain")) or not any_ok)
    calls = trial.get("calls") or []
    return {
        "unit": case["id"],
        "kind": case["kind"],
        "repeat": trial["repeat"],
        "passed": passed,
        "top_correct": top_ok,
        "abstained": abstained,
        "wrong_answer": wrong_answer,
        "must_not_hit": must_not_hit,
        "judged": bool((trial.get("output") or {}).get("judged")),
        "stage_errors": [f"{c.get('stage')}:{(c.get('error') or {}).get('kind')}" for c in calls if not c.get("ok")],
        "refusals": sum(1 for c in calls if c.get("refusal")),
        "latency_ms": trial.get("latency_ms"),
        "cost_usd_uncached": sum(c.get("cost_usd_uncached") or 0.0 for c in calls) if any(c.get("cost_usd_uncached") is not None for c in calls) else None,
        "top": (candidates[0].get("canonical_name") if candidates else None),
        "needs_check": bool(case.get("needs_check")),
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    return {
        "trials": n,
        "pass_rate": sum(r["passed"] for r in rows) / n if n else None,
        "wrong_answers": sum(r["wrong_answer"] for r in rows),
        "must_not_hits": sum(r["must_not_hit"] for r in rows),
        "abstentions": sum(r["abstained"] for r in rows),
        "judged_share": sum(r["judged"] for r in rows) / n if n else None,
        "trials_with_stage_error": sum(1 for r in rows if r["stage_errors"]),
        "refusals": sum(r["refusals"] for r in rows),
        "latency_s_median": (median([r["latency_ms"] for r in rows]) or 0) / 1000 if rows else None,
        "latency_s_p90": _p90([r["latency_ms"] for r in rows]),
        "cost_usd_per_query_mean": mean([r["cost_usd_uncached"] for r in rows]),
        "pass_rate_by_kind": {k: sum(r["passed"] for r in rows if r["kind"] == k) / max(1, sum(1 for r in rows if r["kind"] == k)) for k in sorted({r["kind"] for r in rows})},
        "failed_cases": sorted({r["unit"] for r in rows if not r["passed"]}),
    }


def _p90(values: list) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    return vals[min(len(vals) - 1, int(round(0.9 * (len(vals) - 1))))] / 1000
