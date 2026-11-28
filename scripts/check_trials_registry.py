"""Check that every clinical trial a GeneGuidelines site serves exists in ClinicalTrials.gov, and that its status matches.

    python scripts/check_trials_registry.py https://geneguidelines.genequest.org

Reads GET <site>/api/trials (public), then asks the registry for each NCT identifier. Sends nothing but the identifier. Exit code 1 when an identifier is unknown to the registry: such a trial is either invented or mistyped, and must not be shown to families. Status differences are printed and do not fail the run. Written after two invented trials were found in production on 2026-11-28.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

REGISTRY = "https://clinicaltrials.gov/api/v2/studies/{nct}?fields=protocolSection.statusModule.overallStatus"


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "trials-registry-check"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main(site: str) -> int:
    served = json.loads(_get(site.rstrip("/") + "/api/trials"))
    trials = {t["nct"]: t for t in (served if isinstance(served, list) else served.get("trials", []))}
    unknown: list[str] = []
    differs: list[str] = []
    for nct, trial in sorted(trials.items()):
        try:
            record = json.loads(_get(REGISTRY.format(nct=nct)))
        except urllib.error.HTTPError as exc:
            unknown.append(f"{nct} (HTTP {exc.code}) {trial.get('diseases')} shown as {trial.get('status')!r}: {trial.get('title')}")
            continue
        registry_status = record.get("protocolSection", {}).get("statusModule", {}).get("overallStatus", "")
        ours = str(trial.get("status") or "").upper().replace("-", "_")
        if registry_status and ours and registry_status.upper() != ours:
            differs.append(f"{nct} {trial.get('diseases')}: site {trial.get('status')!r}, registry {registry_status!r}")
        time.sleep(0.15)
    print(f"{len(trials)} trials served; {len(unknown)} unknown to the registry; {len(differs)} with a different status")
    for row in unknown:
        print("UNKNOWN ", row)
    for row in differs:
        print("STATUS  ", row)
    return 1 if unknown else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
