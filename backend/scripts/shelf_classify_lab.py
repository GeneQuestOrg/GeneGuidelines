"""Bench the shelf classifier before letting it rewrite a live shelf.

The shelf rebuild is a full replace driven by a stochastic classifier with no
memory of what was there before. It has now silently lost good documents twice:
once the paediatric review and the 2012 craniofacial guidelines, and once the 2023
craniofacial review by the NIH group. Nobody noticed until the synthesis was read.

This runs the classify prompt against the real candidate set and reports which
documents survive, so a prompt change can be judged on evidence.

    python3 -m backend.scripts.shelf_classify_lab --variant current --runs 3
    python3 -m backend.scripts.shelf_classify_lab --list
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import sys

os.environ.setdefault("AGENT_NO_MCP", "1")

_SPEC = (
    pathlib.Path(__file__).resolve().parents[1] / "flows" / "specs" / "guideline_shelf_build.json"
)
_CACHE = pathlib.Path("/tmp/gg-shelf-candidates.json")

# The curated FD shelf. These are the documents a human put there on purpose; a
# rebuild that drops one is the failure this file exists to catch.
_EXPECTED = {
    "31196103": "konsensus 2019",
    "38010041": "FD u dzieci 2024",
    "36849642": "Boyce twarzoczaszka 2023",
    "22640797": "wytyczne twarzoczaszki 2012",
    "25043984": "imaging 2014",
    "NBK274564": "GeneReviews",
}


def candidates(disease: str = "Fibrous Dysplasia", gene: str = "GNAS", refresh: bool = False):
    if _CACHE.exists() and not refresh:
        return json.loads(_CACHE.read_text())
    from backend.executors.guideline_shelf_search_executor import (  # noqa: PLC0415
        _collect_shelf_candidates,
    )

    out = _collect_shelf_candidates(disease, gene)
    _CACHE.write_text(json.dumps(out))
    return out


def live_prompt() -> str:
    spec = json.loads(_SPEC.read_text())
    return next(n for n in spec["nodes"] if n["node_id"] == "gsb-classify")["prompt"]


def _v_current(base: str) -> str:
    return base


def _v_keep_both_versions(base: str) -> str:
    """Stop treating an older guideline and a newer review as duplicates.

    The classifier dropped a 2023 NIH craniofacial review because 2012 craniofacial
    guidelines already covered the area. Both belong: the older one is the formal
    guideline, the newer one is what the field currently says. The schema already
    has `kind: update` + `updates_note` to express exactly that relationship.
    """
    return base.replace(
        "- Drop duplicates, primary research that isn't review/consensus, and clearly off-topic hits.\n"
        "- A tight, high-signal shelf beats a long one.",
        "- Drop duplicates, primary research that isn't review/consensus, and clearly off-topic hits.\n"
        "- Two documents on the same sub-area are NOT duplicates when one is newer. Keep\n"
        "  both and mark the newer one kind=update with an updates_note saying what it\n"
        "  changes. A formal guideline and a later review of the same region are the\n"
        "  clearest example: the guideline is what was agreed, the review is where the\n"
        "  field is now, and a clinician wants both. Only call something a duplicate when\n"
        "  it genuinely adds nothing the other does not already say.\n"
        "- Never drop a document merely to keep the shelf short. Completeness of the\n"
        "  clinically relevant set matters more than brevity; there is ample room.",
        1,
    )


VARIANTS = {"current": _v_current, "keep-both": _v_keep_both_versions}


def run_once(prompt: str) -> dict:
    import asyncio  # noqa: PLC0415

    from backend.agents.schemas import GuidelineShelfOutput  # noqa: PLC0415
    from backend.agents.simple_runner import (  # noqa: PLC0415
        resolve_model_spec_for_node,
        run_llm_simple_async,
    )

    node = {"node_id": "gsb-classify-lab", "node_type": "prompt"}
    return asyncio.run(
        run_llm_simple_async(
            system_prompt="",
            user_prompt=prompt,
            result_type=GuidelineShelfOutput,
            model_spec=resolve_model_spec_for_node(node),
            max_tokens=8000,
            max_retry=1,
            store={},
            event_queue=None,
            node_id="gsb-classify-lab",
            emit_fn=lambda *a, **k: None,
            poison_store_on_failure=False,
        )
    )


def ids_on_shelf(result: dict) -> set[str]:
    out = set()
    for d in result.get("docs") or []:
        ident = str(d.get("pmid") or d.get("bookshelf") or "").strip()
        if ident:
            out.add(ident)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="current", choices=sorted(VARIANTS))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--disease", default="Fibrous Dysplasia")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        print("warianty:", ", ".join(sorted(VARIANTS)))
        return 0

    cands = candidates(refresh=args.refresh)
    print(f"kandydatów: {len(cands)}", file=sys.stderr)
    prompt = (
        VARIANTS[args.variant](live_prompt())
        .replace("{{ context.gsb-search.candidates }}", json.dumps(cands, ensure_ascii=False))
        .replace("{{ context.initial.disease_name }}", args.disease)
    )
    print(f"prompt: {len(prompt)} znaków ≈ {len(prompt)//4} tokenów\n", file=sys.stderr)

    kept = collections.Counter()
    sizes = []
    for i in range(args.runs):
        got = ids_on_shelf(run_once(prompt))
        sizes.append(len(got))
        for k in _EXPECTED:
            if k in got:
                kept[k] += 1
        missing = [_EXPECTED[k] for k in _EXPECTED if k not in got]
        print(f"  przebieg {i+1}: {len(got)} dok. | brakuje: {missing or 'nic'}")

    print(f"\n=== {args.variant}: średnia wielkość półki {sum(sizes)/len(sizes):.1f}")
    for k, name in _EXPECTED.items():
        print(f"  {kept[k]}/{args.runs}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
