"""Paths, hashing, JSONL and provenance helpers shared by every command of the lab."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXP_DIR.parents[2]
CASES_DIR = EXP_DIR / "cases"
SNAPSHOT_DIR = EXP_DIR / "data" / "snapshots"
RESULTS_DIR = EXP_DIR / "results"
LEDGER_FILE = RESULTS_DIR / "ledger.jsonl"

TASKS = ("synthesis", "pubmed", "search")

# Product files whose content decides what a trial measures. Their hashes go into run.json, so a run is never compared with one made against different product code.
PRODUCT_SOURCES = (
    "backend/agents/schemas.py",
    "backend/agents/simple_runner.py",
    "backend/engine/context_interpolation.py",
    "backend/engine/prompt_formatting.py",
    "backend/flows/specs/guideline_synthesis.json",
    "backend/executors/guidelines/guideline_shelf_load_executor.py",
    "backend/executors/guidelines/guideline_synthesis_writer_executor.py",
    "backend/guidelines/evidence.py",
    "backend/flows/pubmed/prompt_context.py",
    "backend/flows/pubmed/retrieval.py",
    "backend/database.py",
    "backend/services/disease_wider_search.py",
    "backend/scripts/semantic_probe.py",
)


class LabError(Exception):
    """A refusal the user must act on; printed without a traceback."""


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value: Any) -> str:
    return sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def source_hashes(paths: tuple[str, ...] = PRODUCT_SOURCES) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for rel in paths:
        p = REPO_ROOT / rel
        out[rel] = sha256_file(p) if p.is_file() else None
    return out


# The lab files that decide what is sent to a model. A run cannot be continued once these change; scoring files may change, and `score` re-reads the saved answers.
REQUEST_FILES = ("callers.py", "arms.py", "task_search.py", "snapshot.py")


def lab_source_hash(files: tuple[str, ...] | None = None) -> str:
    """One hash over lab files: all of them by default (recorded for the record), or only ``files``."""
    paths = [EXP_DIR / f for f in files] if files else [p for p in sorted(EXP_DIR.rglob("*.py")) if "results" not in p.parts]
    parts = [f"{p.relative_to(EXP_DIR)}:{sha256_file(p)}" for p in paths]
    return sha256_text("\n".join(parts))


def git_state() -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout.strip())
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return None, None


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise LabError(f"{path}:{number} is not valid JSON ({exc.msg})") from exc
    return rows


def append_jsonl(path: Path, row: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def results_path(out: str | Path) -> Path:
    """Run folders live under results/, which git ignores; a bare name means results/<name>."""
    out = Path(out)
    if not out.is_absolute() and out.parts and out.parts[0] != "results":
        out = RESULTS_DIR / out
    elif not out.is_absolute():
        out = EXP_DIR / out
    out = out.resolve()
    if REPO_ROOT in out.parents and RESULTS_DIR.resolve() not in out.parents:
        raise LabError(f"Inside the repository a run goes under {RESULTS_DIR.relative_to(REPO_ROOT)}/, which git ignores")
    return out


def median(values: list[float]) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return float(vals[mid]) if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def mean(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None
