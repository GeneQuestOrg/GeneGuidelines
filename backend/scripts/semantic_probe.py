"""Judge whether a generated section actually *says* something, not whether it
contains a phrase.

Keyword probes gave false alarms the moment the writing got better. Asked whether a
summary tells a family that a biopsy is usually unnecessary, a substring search for
"not routinely" reports failure against:

    "biopsy may be unnecessary or impractical for quiescent, asymptomatic or
     cranial-base lesions when history, examination and classic imaging are adequate"

which is the same clinical claim, better expressed. A check that punishes better
prose is worse than no check, because it trains you to write for the checker.

So the claim is judged by a model, with the rule that only the source text may
decide — the judge is told to ignore what it knows about the disease. That keeps
this a test of the summary, not a second opinion about medicine.
"""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field

os.environ.setdefault("AGENT_NO_MCP", "1")

# Judging is a small, cheap job — deliberately not the model under test, so a model
# is never asked to mark its own homework.
_JUDGE_MODEL = "gpt-5.5"


class ClaimVerdict(BaseModel):
    """One claim, judged against the text."""

    present: bool = Field(..., description="True only if the text conveys this claim")
    evidence: str = Field(
        ..., description="The sentence carrying it, verbatim, or '' when absent"
    )


class ProbeVerdicts(BaseModel):
    verdicts: list[ClaimVerdict] = Field(..., min_length=1)


# The claims that made this project exist. Each is a thing a parent needs to be able
# to carry into an appointment; each was missing from production at some point.
FD_DIAGNOSIS_CLAIMS: list[str] = [
    "A biopsy is usually NOT required to diagnose typical fibrous dysplasia — it is "
    "reserved for unusual, questionable cases or suspected malignancy.",
    "Whole-body imaging (bone scintigraphy / nuclear medicine / whole-body MR) is "
    "recommended to establish how much of the skeleton is affected, from about age 5.",
    "Histology alone has limits: it can mislead or come back falsely negative, so "
    "genetic confirmation or repeat sampling may be needed.",
    "Genetic testing for a GNAS variant is indicated when the diagnosis is in doubt, "
    "particularly for a single isolated lesion.",
    "Specific imaging is named for craniofacial disease (for example CT with thin "
    "slices), rather than imaging being described only in general terms.",
]


def judge(text: str, claims: list[str], api_key: str | None = None) -> list[dict[str, Any]]:
    """Ask the judge which claims the text conveys. Returns one verdict per claim."""
    from dotenv import dotenv_values

    from backend.agents.openai_direct import call_structured

    key = api_key or dotenv_values(".env").get("OPENAI_API_KEY")
    numbered = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(claims))
    prompt = (
        "Below is a summary of clinical guidelines, followed by a numbered list of "
        "claims.\n\nFor each claim, decide whether the SUMMARY conveys it — in any "
        "wording. Paraphrase counts; exact phrasing is irrelevant. Judge ONLY from "
        "the summary text: do not use your own knowledge of the disease, and do not "
        "mark a claim present because it is true in general.\n\n"
        "Return one verdict per claim, in order. `evidence` must be a verbatim "
        "sentence from the summary, or an empty string when the claim is absent.\n\n"
        f"=== SUMMARY ===\n{text}\n\n=== CLAIMS ===\n{numbered}\n"
    )
    out = call_structured(
        model=_JUDGE_MODEL,
        prompt=prompt,
        result_type=ProbeVerdicts,
        api_key=key,
        max_completion_tokens=8_000,
    )
    verdicts = out.get("verdicts") or []
    # Never let a short reply silently shrink the claim set — an unjudged claim is
    # unknown, not absent.
    while len(verdicts) < len(claims):
        verdicts.append({"present": False, "evidence": "", "unjudged": True})
    return verdicts[: len(claims)]


def report(text: str, claims: list[str] = FD_DIAGNOSIS_CLAIMS) -> int:
    verdicts = judge(text, claims)
    hits = 0
    for claim, v in zip(claims, verdicts):
        ok = bool(v.get("present"))
        hits += ok
        mark = "TAK" if ok else " - "
        print(f"  [{mark}] {claim[:74]}")
        if ok and v.get("evidence"):
            print(f"        „{v['evidence'][:120]}”")
    print(f"\n  {hits}/{len(claims)} twierdzeń obecnych")
    return hits


if __name__ == "__main__":
    import sys

    payload = sys.stdin.read()
    try:
        data = json.loads(payload)
        body = " ".join(
            p.get("text", "")
            for s in data.get("sections", [data])
            for p in s.get("paragraphs", [])
        )
    except json.JSONDecodeError:
        body = payload
    raise SystemExit(0 if report(body) else 1)
