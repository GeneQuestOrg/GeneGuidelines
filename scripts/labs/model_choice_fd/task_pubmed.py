"""Task 2: the PubMed draft for FD, the two LLM steps that read and cite papers.

- ``pass1-diagnostics`` (evidence pass): reads the 80 abstracts the product puts in the prompt and returns key findings, strength of evidence, contradictions, gaps and the key PMIDs. This is the step that selects and assesses papers.
- ``pm-4-diagnostics`` (drafting, the "pm-4" step that fails with "Unterminated string"): writes the diagnostics section as HTML with inline PMID citations, under the product's 4,000-token output budget.

A trial is one unit in one repeat. Selection agreement between models is computed in ``compare`` (it needs several runs).
"""

from __future__ import annotations

import html
import random
import re

from .common import mean, median

TASK = "pubmed"
_PMID_IN_PROMPT = re.compile(r"PMID:\s*(\d{6,9})")
_INDEXED_ARTICLE = re.compile(r"^\[(\d+)\] .*\n\s*PMID: (\d{6,9})", re.MULTILINE)
_NUMBER = re.compile(r"(?<!\d)(\d{1,9})(?!\d)")
_TABLE_ROW = re.compile(r"^(\d{6,9}) \| ", re.MULTILINE)
_PMID_IN_TEXT = re.compile(r"(?<!\d)(\d{7,9})(?!\d)")
_TAG = re.compile(r"<[^>]+>")


def units(snapshot: dict) -> list[dict]:
    return snapshot["units"]


def result_type(unit: dict):
    from backend.agents.dynamic_output_schema import build_model_from_output_schema_json

    model, err = build_model_from_output_schema_json(unit["output_schema"])
    if err or model is None:
        raise ValueError(f"{unit['unit']}: {err}")
    return model


def stub_output(result_type, unit: str, user: str) -> dict:
    pmids = _PMID_IN_PROMPT.findall(user) or _TABLE_ROW.findall(user)
    first = pmids[0] if pmids else "31196103"
    out = {}
    for name, field in result_type.model_fields.items():
        ann = field.annotation
        if ann is int:
            out[name] = 1
        elif name == "key_pmids_cited":
            out[name] = first
        elif name == "section_html":
            out[name] = f"<p>Stub diagnostics paragraph (PMID {first}).</p>"
        else:
            out[name] = f"stub {name}"
    return out


def allowed_pmids(unit: dict) -> set[str]:
    """The PMIDs the prompt itself offers: the 80 abstracts (evidence pass) or the reference table (drafting)."""
    found = _PMID_IN_PROMPT.findall(unit["user"]) if unit["unit"].startswith("pass1") else _TABLE_ROW.findall(unit["user"])
    return set(found)


def plain(text: str) -> str:
    return html.unescape(_TAG.sub(" ", text or ""))


def index_map(unit: dict) -> dict[str, str]:
    """The evidence-pass prompt numbers its articles [1]..[80] next to their PMIDs; some answers cite the numbers."""
    return dict(_INDEXED_ARTICLE.findall(unit["user"])) if unit["unit"].startswith("pass1") else {}


def cited_pmids(unit_name: str, output: dict, indexes: dict[str, str] | None = None) -> tuple[list[str], int]:
    """(PMIDs cited, how many were given as article numbers instead of PMIDs). Article numbers are resolved through the prompt's own numbering, so selection can still be compared, and counted, because the product shows that field to readers as "Cytowane PMID"."""
    if unit_name.startswith("pass1"):
        found, by_index = set(), 0
        for number in _NUMBER.findall(str(output.get("key_pmids_cited") or "")):
            if len(number) >= 6:
                found.add(number)
            elif indexes and number in indexes:
                found.add(indexes[number])
                by_index += 1
        return sorted(found), by_index
    return sorted(set(_PMID_IN_TEXT.findall(plain(str(output.get("section_html") or ""))))), 0


def score_trial(snapshot: dict, trial: dict) -> dict:
    unit = next(u for u in snapshot["units"] if u["unit"] == trial["unit"])
    calls = trial.get("calls") or []
    call = calls[-1] if calls else {}
    output = trial.get("output") or {}
    allowed = allowed_pmids(unit)
    corpus = set(snapshot["corpus_pmids"])
    cited, by_index = cited_pmids(unit["unit"], output, index_map(unit)) if output else ([], 0)
    usage = call.get("usage") or {}
    text = plain(str(output.get("section_html") or "")) if unit["unit"].startswith("pm-4") else str(output.get("key_findings") or "")
    return {
        "unit": trial["unit"],
        "repeat": trial["repeat"],
        "ok": bool(output),
        "first_attempt_ok": bool(call.get("first_attempt_ok")),
        "attempts": len(call.get("attempts") or []),
        "error_kind": (trial.get("error") or {}).get("kind"),
        "truncated": (call.get("error") or {}).get("kind") in ("truncated", "truncated_or_invalid_json") or call.get("stop_reason") == "max_tokens" or any(a.get("error") == "truncated_or_invalid_json" for a in call.get("attempts") or []),
        "refusal": (call.get("refusal") or {}).get("category") if call.get("refusal") else None,
        "cited": cited,
        "cited_count": len(cited),
        "cited_as_article_number": by_index,
        "cited_not_in_prompt": sorted(set(cited) - allowed),
        "cited_not_retrieved": sorted(set(cited) - corpus),
        "evidence_needed_markers": text.lower().count("evidence needed"),
        "text_chars": len(text),
        "latency_ms": call.get("latency_ms"),
        "cost_usd_uncached": call.get("cost_usd_uncached"),
        "input_tokens": int(usage.get("input_tokens") or 0) + int(usage.get("cache_read_input_tokens") or 0) + int(usage.get("cache_creation_input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
    }


def judged_text(trials: list[dict]) -> str:
    """What the claim judge reads for one repeat: the evidence pass's key findings only. The drafted section is left out because its prompt never receives the evidence pass or the consensus abstracts (see README), so its content says more about the model's memory than about the papers."""
    parts = [str((t.get("output") or {}).get("key_findings") or "") for t in sorted(trials, key=lambda x: x["unit"]) if t["unit"].startswith("pass1")]
    return "\n\n".join(p for p in parts if p.strip())


def summarize(rows: list[dict]) -> dict:
    out = {}
    for unit in sorted({r["unit"] for r in rows}):
        rs = [r for r in rows if r["unit"] == unit]
        out[unit] = {
            "trials": len(rs),
            "ok": sum(r["ok"] for r in rs),
            "first_attempt_ok": sum(r["first_attempt_ok"] for r in rs),
            "truncated_trials": sum(bool(r["truncated"]) for r in rs),
            "refusals": sum(1 for r in rs if r["refusal"]),
            "cited_mean": mean([r["cited_count"] for r in rs if r["ok"]]),
            "trials_citing_article_numbers": sum(1 for r in rs if r.get("cited_as_article_number")),
            "cited_not_in_prompt_total": sum(len(r["cited_not_in_prompt"]) for r in rs),
            "trials_with_pmid_outside_prompt": sum(1 for r in rs if r["cited_not_in_prompt"]),
            "evidence_needed_markers_mean": mean([r["evidence_needed_markers"] for r in rs if r["ok"]]),
            "text_chars_mean": mean([r["text_chars"] for r in rs if r["ok"]]),
            "latency_s_median": (median([r["latency_ms"] for r in rs]) or 0) / 1000 if any(r["latency_ms"] for r in rs) else None,
            "cost_usd_mean": mean([r["cost_usd_uncached"] for r in rs]),
            "input_tokens_mean": mean([r["input_tokens"] for r in rs]),
            "output_tokens_mean": mean([r["output_tokens"] for r in rs]),
        }
    return out


def jaccard(a: set, b: set) -> float | None:
    if not a and not b:
        return None
    return len(a & b) / len(a | b)


def selection_sets(rows: list[dict]) -> list[set[str]]:
    return [set(r["cited"]) for r in rows if r["unit"].startswith("pass1") and r["ok"]]


def mean_cross_agreement(left: list[set], right: list[set], same: bool = False) -> float | None:
    pairs = [(i, j) for i in range(len(left)) for j in range(len(right)) if not (same and j <= i)]
    return mean([jaccard(left[i], right[j]) for i, j in pairs])


def sample_citations(snapshot: dict, trials: list[dict], n: int, seed: int) -> list[dict]:
    """Sentences of the drafted section that cite a PMID, with that paper's abstract from the snapshot, for the hand check."""
    abstracts = {a["pmid"]: a for a in snapshot["corpus"]}
    pool = []
    for t in trials:
        if not t["unit"].startswith("pm-4") or not t.get("output"):
            continue
        text = plain(str(t["output"].get("section_html") or ""))
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            for pmid in set(_PMID_IN_TEXT.findall(sentence)):
                pool.append({"sentence": sentence.strip()[:700], "pmid": pmid})
    rng = random.Random(seed)
    rng.shuffle(pool)
    out = []
    for item in pool[:n]:
        paper = abstracts.get(item["pmid"])
        out.append({**item, "title": (paper or {}).get("title") or "(PMID not among the papers the product retrieved)", "abstract": ((paper or {}).get("abstract") or "")[:2500]})
    return out
