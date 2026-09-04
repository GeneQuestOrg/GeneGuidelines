"""Bench one synthesis section prompt against the real shelf, before deploying it.

Prompt changes to the guideline synthesis have twice reached production untested
and twice behaved differently than expected — once emptying every section on
gemma-4-31B while working on gpt-5.5, once producing an encyclopedia entry that
cited a single document. This runs a prompt variant against the *real* FD shelf,
with the *same* model production uses, and scores the output on the things we
actually care about.

Usage:
    python3 -m backend.scripts.synthesis_prompt_lab --section diagnosis
    python3 -m backend.scripts.synthesis_prompt_lab --section diagnosis --variant v2
    python3 -m backend.scripts.synthesis_prompt_lab --list

Variants live in ``VARIANTS`` below. "current" always reads the live prompt out of
backend/flows/specs/guideline_synthesis.json, so it is a real baseline rather than
a copy that drifts.

The shelf is fetched once and cached on disk, because pulling 80 kB of full text
from NCBI for every variant is slow and rude.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time

os.environ.setdefault("AGENT_NO_MCP", "1")

_CACHE = pathlib.Path("/tmp/gg-shelf-cache.json")
_SPEC = pathlib.Path(__file__).resolve().parents[1] / "flows" / "specs" / "guideline_synthesis.json"

# What we check the output for. These are the failures actually seen in production,
# not a generic quality rubric.
_PROBES: dict[str, list[str]] = {
    "biopsy not routinely needed": ["not routinely", "only necessary", "reserved for"],
    "scintigraphy named": ["scintigraph", "99mtc", "spect", "naf pet", "nuclear medicine"],
    "histology limits / false negatives": ["false negative", "repeated", "fresh-frozen", "fresh or"],
    "genetic testing guidance": ["genetic testing", "gnas", "sequencing"],
}

# Probes that need two things present at once. The whole-body-imaging probe used to
# match on "extent of", which the model satisfies with "used to identify the full
# extent of skeletal disease" — the modality without the recommendation. What makes
# that line worth bringing to a doctor is its SCOPE: for every patient over five. So
# require both the modality and the scope.
_PAIRED_PROBES: dict[str, tuple[list[str], list[str]]] = {
    "whole-body imaging FOR ALL ≥5y": (
        ["whole body", "whole-body", "scintigraph", "nuclear medicine", "spect"],
        ["5 years", "age 5", "aged 5", "over 5", "all patients"],
    ),
}


def load_shelf(slug: str = "fd", refresh: bool = False) -> list[dict]:
    """The real shelf documents with full text, cached on disk."""
    if _CACHE.exists() and not refresh:
        return json.loads(_CACHE.read_text())

    from backend.guidelines.deps import provide_guidelines_repo  # noqa: PLC0415
    from backend.tools.pmc_fulltext import (  # noqa: PLC0415
        _pmid_to_pmcid,
        fetch_fulltext_sections,
        render_for_prompt,
    )
    from backend.tools.pubmed_runtime import fetch_article_details_impl  # noqa: PLC0415

    repo = provide_guidelines_repo()
    docs = repo.list_source_documents(slug)
    pmids = [d.pmid for d in docs if d.pmid]
    abstracts = {
        str(a.get("pmid")): a.get("abstract") or ""
        for a in (fetch_article_details_impl(pmids, include_abstracts=True).get("articles") or [])
    }
    pmcids = _pmid_to_pmcid(pmids)

    out = []
    for d in docs:
        pmid = d.pmid or ""
        full = ""
        if pmid in pmcids:
            full = render_for_prompt(fetch_fulltext_sections(pmid, pmcids[pmid]), 120_000)
        out.append(
            {
                "docId": d.doc_id,
                "role": d.role,
                "pmid": pmid or None,
                "title": d.title,
                "scope": d.scope,
                "covers": list(d.covers),
                "abstract": abstracts.get(pmid, ""),
                "fullText": full,
                "textSource": "full-text" if full else "abstract",
            }
        )
    _CACHE.write_text(json.dumps(out))
    return out


def live_prompt(section: str) -> str:
    spec = json.loads(_SPEC.read_text())
    node = next(n for n in spec["nodes"] if n["node_id"] == f"gs-sec-{section}")
    return node["prompt"]


# ---------------------------------------------------------------------------
# Variants. Each takes the live prompt and returns a modified one, so a variant
# only expresses its own delta and cannot silently drift from the baseline.
# ---------------------------------------------------------------------------

def _v_current(base: str) -> str:
    return base


def _v_cover_the_shelf(base: str) -> str:
    """Force the model off the single most authoritative document.

    Production drew 20 of 21 paragraphs from the consensus and ignored the 2023
    craniofacial review entirely.
    """
    return base.replace(
        "What this section is FOR",
        """Use the WHOLE shelf, not just the most authoritative document:
- The consensus document is the base, but the other documents are on the shelf
  because they cover something it does not — a newer review, a specific anatomy, a
  specific age group. Read each document's scope and covers before you write.
- If a shelf document carries anything relevant to this section, at least one
  paragraph must be drawn from it. Do not let one document supply every paragraph
  when others have relevant content.
- Where two documents address the same point, prefer the more recent one and set
  the update field.

What this section is FOR""",
        1,
    )


def _v_named_investigations(base: str) -> str:
    """Force the concrete named test out of the source.

    "whole body imaging using bone scintigraphy … for all patients ≥ age 5 years"
    was present in the source text and inside the character budget, and the model
    still wrote around it.
    """
    return base.replace(
        "- State explicitly what is NOT recommended",
        """- Name the actual investigations, thresholds and ages the source states. If the
  source says which test, at what age, or how often, that belongs in the summary
  verbatim in substance — "whole body imaging should be considered for all patients
  over 5" is the kind of sentence a family can act on; "imaging is used to assess
  the disease" is not.
- State explicitly what is NOT recommended""",
        1,
    )


def _v_both(base: str) -> str:
    return _v_named_investigations(_v_cover_the_shelf(base))


def _v_tail_checklist(base: str) -> str:
    """One short requirement, placed last — closest to the point of generation.

    The verbose blocks in the other variants may simply be diluting attention; this
    tests the opposite hypothesis with a single sentence naming the mechanism.
    """
    return base.rstrip() + (
        "\n\nBefore you answer: look at every shelf document whose textSource is "
        '"full-text". If more than one has content relevant to this section, draw at '
        "least one paragraph from each of them. A section sourced entirely from the "
        "single largest document is a failure, not a safe default.\n"
    )


def _v_more_paragraphs(base: str) -> str:
    """Option (c): give each section more room, so recommendations stop competing."""
    return base.replace(
        "- Write one short orienting sentence, then 2-5 paragraphs.",
        "- Write one short orienting sentence, then 4-8 paragraphs.",
        1,
    )


VARIANTS = {
    "current": _v_current,
    "more-paragraphs": _v_more_paragraphs,
    "tail-checklist": _v_tail_checklist,
    "cover-shelf": _v_cover_the_shelf,
    "named-tests": _v_named_investigations,
    "both": _v_both,
}


def render(prompt: str, shelf: list[dict], disease: str) -> str:
    """Substitute the two template variables the flow would fill in."""
    return prompt.replace(
        "{{ context.gs-shelf.shelf_docs }}", json.dumps(shelf, ensure_ascii=False)
    ).replace("{{ context.initial.disease_name }}", disease)


def run_once(prompt: str) -> dict:
    """One call through the same runner and schema the flow uses."""
    import asyncio  # noqa: PLC0415

    from backend.agents.schemas import GuidelineSectionOutput  # noqa: PLC0415
    from backend.agents.simple_runner import (  # noqa: PLC0415
        resolve_model_spec_for_node,
        run_llm_simple_async,
    )

    node = {"node_id": "gs-sec-lab", "node_type": "prompt"}
    return asyncio.run(
        run_llm_simple_async(
            system_prompt="",
            user_prompt=prompt,
            result_type=GuidelineSectionOutput,
            model_spec=resolve_model_spec_for_node(node),
            max_tokens=8000,
            max_retry=1,
            store={},
            event_queue=None,
            node_id="gs-sec-lab",
            emit_fn=lambda *a, **k: None,
            poison_store_on_failure=False,
        )
    )


def score(result: dict) -> dict:
    paras = result.get("paragraphs") or []
    text = " ".join(p.get("text", "") for p in paras).lower()
    docs = {(p.get("source") or {}).get("doc") for p in paras}
    probes = {k: any(t in text for t in terms) for k, terms in _PROBES.items()}
    probes.update(
        {
            k: any(a in text for a in left) and any(b in text for b in right)
            for k, (left, right) in _PAIRED_PROBES.items()
        }
    )
    return {
        "paragraphs": len(paras),
        "chars": len(text),
        "docs_used": sorted(d for d in docs if d),
        "probes": probes,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", default="diagnosis")
    ap.add_argument("--variant", default="current", choices=sorted(VARIANTS))
    ap.add_argument("--disease", default="Fibrous Dysplasia")
    ap.add_argument("--refresh-shelf", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        print("warianty:", ", ".join(sorted(VARIANTS)))
        return 0

    shelf = load_shelf(refresh=args.refresh_shelf)
    print(f"półka: {len(shelf)} dokumentów", file=sys.stderr)
    for d in shelf:
        n = len(d["fullText"]) or len(d["abstract"])
        print(f"  {d['docId']:10} {d['textSource']:10} {n:6} znaków  {d['title'][:48]}", file=sys.stderr)

    prompt = render(VARIANTS[args.variant](live_prompt(args.section)), shelf, args.disease)
    print(f"\nprompt: {len(prompt)} znaków ≈ {len(prompt)//4} tokenów", file=sys.stderr)

    t0 = time.time()
    result = run_once(prompt)
    took = time.time() - t0

    s = score(result)
    print(f"\n=== {args.section} / {args.variant} ({took:.0f}s)")
    print(f"akapitów: {s['paragraphs']} | znaków: {s['chars']} | źródła: {s['docs_used']}")
    for k, v in s["probes"].items():
        print(f"  [{'TAK' if v else '  -'}] {k}")
    print()
    for p in result.get("paragraphs") or []:
        src = p.get("source") or {}
        print(f"• {p.get('text')}")
        print(f"  [{src.get('doc')} · {src.get('loc','')}]\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
