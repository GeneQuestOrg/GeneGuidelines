"""Run the notebook's workflow logic locally with Ollama as Gemma stand-in.

This is the "tylko sprawdź czy działa" check — exercises the exact PubMed
fetch + rank-with-LLM + verify pipeline that the notebook will run on
Kaggle, swapping the transformers loader for the running ``ollama`` daemon
on ``http://localhost:11434/v1`` so we can confirm the prompts produce
acceptable picks before publishing.

We do not import ``find_the_consensus.py`` directly because that module
executes its demo + benchmark cells at import time (notebook-style); we
copy-reuse only the pure pipeline pieces from it so we exercise the same
prompts and parser without triggering the model loader.

If Ollama is not running:
    ollama serve &
    ollama pull gemma4:26b   # or gemma3:4b for a fast smoke test
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

# Reuse pipeline helpers (PubMed fetch, JSON parser, prompts, benchmark cases)
# from the notebook source. The import-side-effect demo at the bottom of
# find_the_consensus.py is gated behind ``__main__`` so a plain import is safe.

import ast as _ast


def _load_pure_module():
    """Load find_the_consensus.py but strip top-level demo/benchmark blocks.

    The notebook source executes cells at import time. We keep only:
      - import statements
      - function / class definitions
      - assignments whose target is ALL_CAPS (constants — RANKING_SYSTEM_PROMPT,
        BENCHMARK, PUBMED, USER_AGENT, NCBI_KEY, OUT_DIR, GEMMA_*)
    Everything else (demo print/run statements, benchmark loops, lowercase
    intermediate vars like ``marfan_pmids``) is dropped.
    """
    src = (HERE / "find_the_consensus.py").read_text(encoding="utf-8")
    tree = _ast.parse(src)
    keep = []
    for node in tree.body:
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef, _ast.Import, _ast.ImportFrom)):
            keep.append(node)
            continue
        if isinstance(node, _ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, _ast.Name)]
            if not targets:
                continue
            # Keep ALL_CAPS and "_capsAlias" constants; drop demo intermediates.
            if all(t.isupper() or (t.startswith("_") and t[1:].isupper()) for t in targets):
                keep.append(node)
            continue
        if isinstance(node, _ast.AnnAssign):
            tgt = getattr(node.target, "id", "")
            if tgt and (tgt.isupper() or (tgt.startswith("_") and tgt[1:].isupper())):
                keep.append(node)
            continue
        # Skip top-level Expr (prints, demo calls), For, If, etc.
    tree.body = keep
    tree.body.append(_ast.parse("GEMMA = None").body[0])
    code = compile(tree, str(HERE / "find_the_consensus.py"), "exec")
    import types
    mod = types.ModuleType("find_the_consensus_helpers")
    mod.__file__ = str(HERE / "find_the_consensus.py")
    sys.modules[mod.__name__] = mod  # dataclass decorator looks here
    exec(code, mod.__dict__)
    return mod.__dict__


def _ollama_reachable() -> bool:
    try:
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=1)
        return True
    except Exception:
        return False


def _ollama_chat(model: str, system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> str:
    """OpenAI-compat call against local Ollama. Retries once on empty content
    because Gemma 4 occasionally returns an empty completion with finish_reason=stop
    when the model template handshake glitches on first turn."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    last = ""
    for attempt in range(2):
        req = urllib.request.Request(
            "http://localhost:11434/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.load(r)
        content = (data["choices"][0]["message"]["content"] or "").strip()
        if content:
            return content
        last = content
    return last


def main() -> int:
    if not _ollama_reachable():
        print("Ollama not running on :11434 — skipping local LLM test.")
        print("To verify with the real model: ollama serve & ollama pull gemma4:26b")
        return 1

    ns = _load_pure_module()
    model_name = "gemma4:26b"

    class _OllamaRanker:
        mode = f"ollama-local ({model_name})"

        def rank(self, system_prompt: str, user_prompt: str, max_new_tokens: int = 600) -> str:
            return _ollama_chat(model_name, system_prompt, user_prompt, max_new_tokens)

    ns["GEMMA"] = _OllamaRanker()
    print(f"Using ollama model: {model_name}")

    pubmed_search = ns["pubmed_search"]
    pubmed_summary = ns["pubmed_summary"]
    rank_consensus = ns["rank_consensus"]
    cases = ns["BENCHMARK"]

    results = []
    for case in cases:
        print()
        print(f"-- {case['name']} --")
        pmids = pubmed_search(case["name"], retmax=10)
        print(f"   PubMed candidates: {len(pmids)}: {pmids[:8]}")
        if not pmids:
            results.append({**case, "verdict": "no-candidates", "picked": None})
            continue
        candidates = pubmed_summary(pmids)
        expected_in = case["expected_pmid"] in {c["pmid"] for c in candidates}
        if not candidates:
            results.append({**case, "verdict": "no-summaries", "picked": None})
            continue
        t0 = time.time()
        try:
            pick = rank_consensus(case["name"], candidates)
        except Exception as exc:
            print(f"   FAILED: {exc}")
            results.append({**case, "verdict": "error", "picked": None, "error": str(exc)[:160]})
            continue
        elapsed = time.time() - t0
        match = pick.best_pmid == case["expected_pmid"]
        in_candidates = pick.best_pmid in {c["pmid"] for c in candidates}
        verdict = (
            "EXACT" if match
            else ("REASONABLE-PICK" if (in_candidates and not expected_in)
                  else ("MISS" if expected_in else "CANDIDATE-GAP"))
        )
        print(
            f"   picked PMID {pick.best_pmid:<10} conf={pick.confidence:.2f} "
            f"(expected {case['expected_pmid']}) {verdict} [{elapsed:.1f}s]"
        )
        print(f"   {pick.title[:90]}")
        print(f"   reasoning: {pick.reasoning[:180]}")
        results.append({
            **case,
            "picked": pick.best_pmid,
            "title": pick.title,
            "verdict": verdict,
            "confidence": pick.confidence,
            "elapsed_sec": round(elapsed, 1),
            "expected_in_candidates": expected_in,
        })

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    exact = sum(1 for r in results if r.get("verdict") == "EXACT")
    reasonable = sum(1 for r in results if r.get("verdict") in {"EXACT", "REASONABLE-PICK"})
    print(f"Exact match:            {exact}/{len(cases)}")
    print(f"Exact or reasonable:    {reasonable}/{len(cases)} (picked-from-list, in-scope paper)")
    for r in results:
        print(
            f"  {r['name']:<22} expected={r['expected_pmid']:<10} "
            f"got={str(r.get('picked','?')):<10} {r.get('verdict','?')}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
