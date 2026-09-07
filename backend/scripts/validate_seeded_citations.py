"""Check every seeded doctor publication against PubMed — title AND authorship.

Written after four of the five seeded publications turned out to be fabricated: real
PMIDs carrying invented titles, attributed to real scientists who did not write them.
The unit test guards the allow-list; this does the live check that fills it in.

    python3 -m backend.scripts.validate_seeded_citations

Exits non-zero when anything disagrees, so it can be run before a release.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import urllib.request

_SEED = pathlib.Path(__file__).resolve().parents[1] / "content_doctors.json"
_ESUMMARY = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    "?db=pubmed&retmode=json&id={ids}"
)


def _surname(name: str) -> str:
    """'Dr. Natasha Appelman-Dijkstra' -> 'appelman-dijkstra'."""
    cleaned = re.sub(r"^(dr|prof|mr|ms|mrs)\.?\s+", "", name.strip(), flags=re.I)
    parts = [p for p in re.split(r"\s+", cleaned) if p]
    return parts[-1].lower() if parts else ""


def _normalise(text: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def main() -> int:
    data = json.loads(_SEED.read_text(encoding="utf-8"))
    rows = data.get("doctors", data) if isinstance(data, dict) else data
    claims = [
        (str(doc.get("slug", "?")), str(doc.get("name", "")), str(pub.get("pmid", "")), str(pub.get("title", "")))
        for doc in rows
        for pub in (doc.get("publications") or [])
    ]
    if not claims:
        print("no seeded publications to check.")
        return 0

    ids = sorted({pmid for _, _, pmid, _ in claims if pmid})
    with urllib.request.urlopen(_ESUMMARY.format(ids=",".join(ids)), timeout=90) as resp:
        result = json.load(resp)["result"]

    problems = 0
    for slug, name, pmid, title in claims:
        record = result.get(pmid) or {}
        real_title = record.get("title", "")
        authors = [a.get("name", "") for a in record.get("authors", [])]

        if not real_title:
            print(f"  MISSING   {slug}: PMID {pmid} is not in PubMed")
            problems += 1
            continue

        claimed, actual = _normalise(title), _normalise(real_title)
        overlap = len(claimed & actual) / max(1, len(claimed))
        if overlap < 0.45:
            print(f"  TITLE     {slug}: PMID {pmid}")
            print(f"            seed  : {title}")
            print(f"            PubMed: {real_title}")
            problems += 1

        surname = _surname(name)
        if surname and not any(surname.split("-")[0] in a.lower() for a in authors):
            print(f"  AUTHOR    {slug}: {name} is not among the authors of PMID {pmid}")
            print(f"            authors: {', '.join(authors[:8])}")
            problems += 1

        if overlap >= 0.45 and surname and any(surname.split("-")[0] in a.lower() for a in authors):
            print(f"  OK        {slug}: PMID {pmid}")

    print(f"\n{problems} problem(s) across {len(claims)} seeded publication(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
