"""Task 1: the five synthesis sections written from the FD source shelf (``gs-sec-*`` nodes).

A trial is one section in one repeat. A document is the five sections of one repeat, assembled by the product's own writer logic (``GuidelineSynthesisWriterExecutor._collect_sections``: structural cleaning plus the cross-section duplicate filter), and every metric is computed on that document, as a reader would see it.
"""

from __future__ import annotations

import random
import re
from typing import Any

from .common import mean, median

TASK = "synthesis"


def units(snapshot: dict) -> list[dict]:
    return snapshot["units"]


def result_type(unit: dict):
    from backend.agents.schemas import get_preset_model

    return get_preset_model(unit["schema_key"])


def stub_output(_result_type, unit: str, user: str) -> dict:
    """One paragraph citing the base consensus by a heading that exists in its text."""
    return {"intro": f"Stub for {unit}.", "paragraphs": [{"id": f"{unit}-p1", "text": f"Stub paragraph for {unit}: a biopsy is usually only necessary in unusual or questionable cases.", "source": {"doc": "31196103", "loc": "§ Histological and genetic characterisation"}, "citations": ["31196103"]}]}


def shipped_trials(snapshot: dict, run_name: str) -> list[dict]:
    """The stored production synthesis as one repeat, so it is scored by exactly the same code."""
    out = []
    by_id = {s["id"]: s for s in snapshot["shipped"].get("sections") or []}
    for unit in snapshot["units"]:
        section = by_id.get(unit["section_id"]) or {}
        output = {"intro": section.get("intro") or "", "paragraphs": section.get("paragraphs") or []}
        out.append({"run": run_name, "unit": unit["unit"], "repeat": 1, "input_sha256": None, "calls": [{"provider": "stored-production", "model": "stored synthesis (lastUpdated " + str(snapshot["shipped"].get("lastUpdated")) + ")", "ok": True, "output": output, "first_attempt_ok": True, "usage": {}, "latency_ms": None, "cost_usd": None, "cost_usd_uncached": None, "attempts": [], "error": None, "refusal": None, "stop_reason": None}], "output": output, "error": None})
    return out


# --- scoring ---------------------------------------------------------------------------------------------------------------

_HEADING = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (text or "").lower().replace("§", " "))).strip()


def shelf_index(snapshot: dict) -> dict[str, dict]:
    index = {}
    for doc in snapshot["shelf_docs"]:
        headings = [_norm(h) for h in _HEADING.findall(doc.get("fullText") or "")]
        index[str(doc["docId"])] = {"pmid": doc.get("pmid"), "headings": [h for h in headings if h], "full_text": bool(doc.get("fullText")), "abstract": bool(doc.get("abstract"))}
    return index


def loc_found(loc: str, entry: dict | None) -> bool:
    """Does any part of a paragraph's locator name a real heading of the cited document (or its abstract)?"""
    if not entry or not (loc or "").strip():
        return False
    for part in re.split(r"[;|]", loc):
        p = _norm(part)
        if len(p) < 3:
            continue
        if p in ("abstract", "summary") and entry["abstract"]:
            return True
        for heading in entry["headings"]:
            if p == heading or (len(p) >= 6 and (p in heading or heading in p)):
                return True
    return False


def paragraph_checks(paragraph: dict, index: dict[str, dict], shelf_pmids: set[str]) -> dict:
    from backend.guidelines.evidence import is_paragraph_grounded

    source = paragraph.get("source") or {}
    doc = str(source.get("doc") or "").strip()
    entry = index.get(doc)
    citations = [str(c).strip() for c in paragraph.get("citations") or [] if str(c).strip()]
    citations_valid = all(c in shelf_pmids for c in citations)
    found = loc_found(str(source.get("loc") or ""), entry)
    grounded = is_paragraph_grounded(paragraph)
    return {
        "grounded_adr005": grounded,
        "doc_on_shelf": entry is not None,
        "citations_on_shelf": citations_valid,
        "loc_given": bool(str(source.get("loc") or "").strip()),
        "loc_found": found,
        "anchored_valid": grounded and entry is not None and citations_valid and (found or any(c in shelf_pmids for c in citations)),
    }


def assemble(snapshot: dict, trials: list[dict]) -> list[dict]:
    """Sections as the product's writer would store them, from one repeat's section outputs."""
    from backend.executors.guidelines.guideline_synthesis_writer_executor import (
        GuidelineSynthesisWriterExecutor,
        _normalize_section_specs,
    )

    context = {t["unit"]: t["output"] for t in trials if isinstance(t.get("output"), dict)}
    return GuidelineSynthesisWriterExecutor(repo=object())._collect_sections(context, _normalize_section_specs(snapshot["initial"]["sections"]), {})


def document_text(sections: list[dict]) -> str:
    parts = []
    for s in sections:
        parts.append(f"## {s.get('title') or s.get('id')}")
        if s.get("intro"):
            parts.append(s["intro"])
        parts.extend(p.get("text", "") for p in s.get("paragraphs") or [])
    return "\n\n".join(parts)


def score_document(snapshot: dict, trials: list[dict]) -> dict:
    from backend.guidelines.evidence import grounded_paragraph_count, is_grounded

    index = shelf_index(snapshot)
    shelf_pmids = {str(p) for p in snapshot.get("shelf_pmids") or []}
    sections = assemble(snapshot, trials)
    raw_paragraphs = sum(len((t.get("output") or {}).get("paragraphs") or []) for t in trials)
    paragraphs = [p for s in sections for p in s.get("paragraphs") or []]
    checks = [paragraph_checks(p, index, shelf_pmids) for p in paragraphs]
    calls = [c for t in trials for c in t.get("calls") or []]
    fulltext_docs = {d for d, e in index.items() if e["full_text"]}
    used = {str((p.get("source") or {}).get("doc") or "") for p in paragraphs}
    n = len(paragraphs)
    latencies = [c.get("latency_ms") for c in calls if c.get("latency_ms") is not None]
    costs = [c.get("cost_usd_uncached") for c in calls]
    return {
        "units_expected": len(snapshot["units"]),
        "units_ok": sum(1 for t in trials if t.get("output")),
        "units_first_attempt_ok": sum(1 for t in trials if t.get("calls") and t["calls"][-1].get("first_attempt_ok")),
        "errors": [{"unit": t["unit"], "kind": (t.get("error") or {}).get("kind")} for t in trials if t.get("error")],
        "refusals": sum(1 for c in calls if c.get("refusal")),
        "truncations": sum(1 for c in calls if (c.get("error") or {}).get("kind") in ("truncated", "truncated_or_invalid_json") or c.get("stop_reason") == "max_tokens"),
        "sections_with_paragraphs": sum(1 for s in sections if s.get("paragraphs")),
        "paragraphs": n,
        "paragraphs_dropped_as_duplicates": max(0, raw_paragraphs - n),
        "gate_pass_adr005": is_grounded(sections),
        "grounded_share_adr005": grounded_paragraph_count(sections) / n if n else None,
        "anchored_valid_share": sum(c["anchored_valid"] for c in checks) / n if n else None,
        "loc_found_share": sum(c["loc_found"] for c in checks) / n if n else None,
        "invalid_citation_paragraphs": sum(1 for c in checks if not c["citations_on_shelf"]),
        "doc_not_on_shelf_paragraphs": sum(1 for c in checks if not c["doc_on_shelf"]),
        "fulltext_docs_used": len(used & fulltext_docs),
        "fulltext_docs_on_shelf": len(fulltext_docs),
        "chars": sum(len(p.get("text") or "") for p in paragraphs),
        "latency_ms_sum": sum(latencies) if latencies else None,
        "latency_ms_max": max(latencies) if latencies else None,
        "cost_usd_uncached": sum(c for c in costs if c is not None) if any(c is not None for c in costs) else None,
        "input_tokens": sum(int((c.get("usage") or {}).get("input_tokens") or 0) + int((c.get("usage") or {}).get("cache_read_input_tokens") or 0) + int((c.get("usage") or {}).get("cache_creation_input_tokens") or 0) for c in calls),
        "output_tokens": sum(int((c.get("usage") or {}).get("output_tokens") or 0) for c in calls),
        "text_sha256": __import__("hashlib").sha256(document_text(sections).encode()).hexdigest(),
    }


def summarize(docs: list[dict]) -> dict:
    def m(key):
        return mean([d.get(key) for d in docs])

    return {
        "documents": len(docs),
        "gate_pass_all": all(d.get("gate_pass_adr005") for d in docs) if docs else None,
        "units_failed": sum(d["units_expected"] - d["units_ok"] for d in docs),
        "units_first_attempt_failed": sum(d["units_expected"] - d["units_first_attempt_ok"] for d in docs),
        "refusals": sum(d["refusals"] for d in docs),
        "truncations": sum(d["truncations"] for d in docs),
        "grounded_share_mean": m("grounded_share_adr005"),
        "anchored_valid_share_mean": m("anchored_valid_share"),
        "loc_found_share_mean": m("loc_found_share"),
        "paragraphs_mean": m("paragraphs"),
        "fulltext_docs_used_mean": m("fulltext_docs_used"),
        "invalid_citation_paragraphs": sum(d["invalid_citation_paragraphs"] for d in docs),
        "chars_mean": m("chars"),
        "cost_usd_per_disease_mean": m("cost_usd_uncached"),
        "latency_s_wall_median": (median([d.get("latency_ms_max") for d in docs]) or 0) / 1000 if docs and any(d.get("latency_ms_max") for d in docs) else None,
        "input_tokens_mean": m("input_tokens"),
        "output_tokens_mean": m("output_tokens"),
    }


def sample_paragraphs(snapshot: dict, trials: list[dict], n: int, seed: int) -> list[dict]:
    """Paragraphs of one document for the blind citation check, with the cited part of the source."""
    sections = assemble(snapshot, trials)
    docs = {str(d["docId"]): d for d in snapshot["shelf_docs"]}
    pool = [(s["id"], p) for s in sections for p in s.get("paragraphs") or []]
    rng = random.Random(seed)
    rng.shuffle(pool)
    out = []
    for section_id, p in pool[:n]:
        source = p.get("source") or {}
        doc = docs.get(str(source.get("doc") or ""))
        out.append({"section": section_id, "text": p.get("text"), "doc": source.get("doc"), "loc": source.get("loc"), "citations": p.get("citations") or [], "doc_title": (doc or {}).get("title"), "excerpt": source_excerpt(doc, str(source.get("loc") or ""))})
    return out


def source_excerpt(doc: dict | None, loc: str, limit: int = 2500) -> str:
    if not doc:
        return "(this document is not on the shelf)"
    full = doc.get("fullText") or ""
    if full and loc:
        blocks = re.split(r"\n(?=### )", "\n" + full)
        wanted = [_norm(x) for x in re.split(r"[;|]", loc) if _norm(x)]
        hits = [b.strip() for b in blocks if any(w and (w in _norm(b.split("\n", 1)[0]) or _norm(b.split("\n", 1)[0].replace("###", "")) in w) for w in wanted)]
        if hits:
            text = "\n\n".join(hits)
            return text[:limit] + (" …" if len(text) > limit else "")
    abstract = doc.get("abstract") or ""
    return ("ABSTRACT: " + abstract[:limit]) if abstract else "(no readable text for this document on the shelf)"


def describe(snapshot: dict) -> dict[str, Any]:
    return {"units": [u["unit"] for u in snapshot["units"]], "shelf_docs": len(snapshot["shelf_docs"]), "fulltexts": snapshot.get("fulltexts_fetched"), "prompt_chars": [len(u["system"]) + len(u["user"]) for u in snapshot["units"]]}
