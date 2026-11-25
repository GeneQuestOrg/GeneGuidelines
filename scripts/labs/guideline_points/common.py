"""Paths of the guideline-points lab, and the spend budget the loop's Claude calls go through. Generic helpers (JSON, hashing, git state) and the price table are the model-choice lab's, reused as they are."""

from __future__ import annotations

from pathlib import Path

from scripts.labs.model_choice_fd.common import (
    LabError,
    append_jsonl,
    git_state,
    now_iso,
    read_json,
    sha256_file,
    sha256_text,
    write_json,
)
from scripts.labs.model_choice_fd.pricing import Ledger, call_cost, worst_case_cost

EXP_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXP_DIR.parents[2]
CASES_DIR = EXP_DIR / "cases"
SNAPSHOT_DIR = EXP_DIR / "data" / "snapshots"
RESULTS_DIR = EXP_DIR / "results"
LEDGER_FILE = RESULTS_DIR / "ledger.jsonl"
DEFAULT_CAP_USD = 25.0
API_BASE = "https://geneguidelines.genequest.org/api"

# Product files that decide what a run measures; their hashes go into run.json.
PRODUCT_SOURCES = (
    "backend/agents/anthropic_direct.py",
    "backend/guidelines/points/models.py",
    "backend/guidelines/points/quote_check.py",
    "backend/guidelines/points/sources.py",
    "backend/guidelines/points/loader.py",
    "backend/guidelines/points/prompts.py",
    "backend/guidelines/points/ports.py",
    "backend/guidelines/points/llm.py",
    "backend/guidelines/points/loop.py",
    "backend/guidelines/points/pipeline.py",
    "backend/guidelines/points/bricks/base.py",
    "backend/guidelines/points/bricks/documents.py",
    "backend/guidelines/points/bricks/select.py",
    "backend/guidelines/points/bricks/quote.py",
    "backend/guidelines/points/bricks/summary_en.py",
    "backend/guidelines/points/bricks/question_en.py",
    "backend/guidelines/points/bricks/translate_pl.py",
    "backend/tools/pmc_fulltext.py",
    "backend/tools/bookshelf_fulltext.py",
)

__all__ = [
    "API_BASE", "CASES_DIR", "DEFAULT_CAP_USD", "EXP_DIR", "LEDGER_FILE", "LabBudget", "LabError", "PRODUCT_SOURCES", "REPO_ROOT", "RESULTS_DIR", "SNAPSHOT_DIR",
    "append_jsonl", "git_state", "now_iso", "read_json", "sha256_file", "sha256_text", "source_hashes", "write_json",
]


def source_hashes() -> dict[str, str | None]:
    return {rel: (sha256_file(REPO_ROOT / rel) if (REPO_ROOT / rel).is_file() else None) for rel in PRODUCT_SOURCES}


class LabBudget:
    """The loop's ``Budget``: reserves each call's worst case before it is made (a call that could cross the cap is refused) and records its real cost after."""

    def __init__(self, run_name: str, cap_usd: float = DEFAULT_CAP_USD, path: Path = LEDGER_FILE) -> None:
        self.run_name = run_name
        self.ledger = Ledger(cap_usd=cap_usd, path=path)

    @property
    def spent(self) -> float:
        return self.ledger.spent

    def reserve(self, model: str, prompt_chars: int, max_tokens: int) -> float:
        amount = worst_case_cost(model, prompt_chars, max_tokens)
        self.ledger.reserve(amount)
        return amount

    def settle(self, ticket: float, model: str, usage: dict, role: str, error: str | None) -> float | None:
        cost, _ = call_cost(model, usage)
        self.ledger.settle(ticket, {"run": self.run_name, "model": model, "unit": role, "cost_usd": cost or 0.0, "usage": usage, "error": error})
        return cost
