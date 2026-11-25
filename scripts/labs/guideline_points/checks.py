"""``check``: everything that can be known before a paid call.

Per disease: each shelf document's grade and whether its full text could be read, what the generator would be shown, and the worst-case cost of one generator call. Then the calibration of the deterministic check: every quote of the hand-written FD block must be found verbatim in the FD/MAS consensus as frozen, and every verifier control must pass the check too (or it would never reach the verifier). A failure here is a problem to fix before any paid run.
"""

from __future__ import annotations

from backend.guidelines.points.llm import GENERATOR_NODE_TOKENS, GENERATOR_SPEC
from backend.guidelines.points.models import doc_from_dict
from backend.guidelines.points.prompts import GENERATOR_SYSTEM, render_documents
from backend.guidelines.points.quote_check import DocIndex, check_point
from backend.guidelines.points.sources import select_documents

from .common import worst_case_cost
from .gold import FD_GUIDELINE_DOC, gold_points, verifier_controls
from .snapshot import load_catalog, load_disease


def disease_inputs(snapshot: str, slug: str):
    """The frozen shelf, and what the generator is shown: readable guideline-grade documents about this disease (the relevance check runs with the GeneReviews index)."""
    from backend.guidelines.relevance import identity_from_disease
    from backend.tools.genereviews_index import load_index

    data = load_disease(snapshot, slug)
    docs = [doc_from_dict(d) for d in data["docs"]]
    selected, notes = select_documents(docs, identity=identity_from_disease(data["disease"]), genereviews=load_index())
    return data, docs, selected, notes


def run_check(snapshot: str) -> int:
    from backend.agents.anthropic_direct import parse_spec, reasoning_max_tokens

    problems: list[str] = []
    model, _ = parse_spec(GENERATOR_SPEC)
    for entry in load_catalog(snapshot):
        slug = entry["slug"]
        data, docs, selected, notes = disease_inputs(snapshot, slug)
        print(f"\n== {slug} ({data['name']}): {len(docs)} shelf documents")
        for d in docs:
            mark = "*" if d in selected else " "
            print(f" {mark} {d.doc_id:<12} grade={d.grade or '-'} chars={d.chars:>7}  {d.text_status[:70]}  | {d.title[:60]}")
        prompt_chars = len(GENERATOR_SYSTEM) + len(render_documents(selected))
        print(f"   selected {len(selected)} documents, {prompt_chars} prompt chars, worst case per generator call ${worst_case_cost(model, prompt_chars, reasoning_max_tokens(GENERATOR_NODE_TOKENS)):.2f}")
        for n in notes:
            print(f"   note: {n}")

    _, docs, _, _ = disease_inputs(snapshot, "fd")
    fd_doc = next((d for d in docs if d.doc_id == FD_GUIDELINE_DOC), None)
    if fd_doc is None or not fd_doc.readable:
        problems.append(f"the FD consensus {FD_GUIDELINE_DOC} is not readable in this snapshot")
    else:
        indexes = {fd_doc.doc_id: DocIndex(fd_doc)}
        print("\n== deterministic check on the hand-written FD quotes")
        for p in gold_points():
            result = check_point(p, indexes)
            print(f"  {p.id}: {result.kind:<10} section={result.match.section if result.match else '-'}")
            if not result.ok:
                problems.append(f"gold quote {p.id} fails the verbatim check: {result.message}")
        print("\n== deterministic check on the verifier controls")
        for c in verifier_controls():
            result = check_point(c["point"], indexes)
            omitted = f" omitted={list(result.match.omitted)}" if result.match and result.match.omitted else ""
            print(f"  {c['id']:<14} expect={c['expect']} check={result.kind}{omitted}")
            if not result.ok:
                problems.append(f"control {c['id']} fails the verbatim check, so it can never reach the verifier: {result.message}")
    for problem in problems:
        print(f"  problem: {problem}")
    return 1 if problems else 0
