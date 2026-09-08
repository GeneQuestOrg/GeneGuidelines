"""Re-check the recorded ERN centres against the networks' own pages.

Membership changes: centres join, affiliated partners become full members, hospitals
merge and rename. A recorded accreditation that has quietly lapsed is the same class
of defect as a fabricated citation — a claim the source no longer supports — so this
re-reads the page each centre was taken from and reports drift.

    python3 -m backend.scripts.validate_ern_centres

Exits non-zero when a centre can no longer be found on its source page. It cannot
prove the reverse (that a page has ADDED centres we do not carry); for that, read the
page and add them.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unicodedata
import urllib.request

_CENTRES = pathlib.Path(__file__).resolve().parents[1] / "ern_centres.json"
_USER_AGENT = "GeneQuestFoundation/1.0 (https://genequest.org; darek@genequest.org)"


def _normalise(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8", "replace")


def main() -> int:
    data = json.loads(_CENTRES.read_text(encoding="utf-8"))
    centres = data.get("centres") or []
    if not centres:
        print("no centres recorded.")
        return 0

    pages: dict[str, str] = {}
    problems = 0
    for centre in centres:
        url = str(centre.get("sourceUrl") or "")
        name = str(centre.get("name") or "")
        city = str(centre.get("city") or "")
        if url not in pages:
            try:
                pages[url] = _normalise(_fetch(url))
            except Exception as exc:  # noqa: BLE001 — a fetch failure is not a lapsed centre
                print(f"  UNREACHABLE  {url}: {exc}")
                pages[url] = ""
                problems += 1
        page = pages[url]
        if not page:
            continue

        # Match on the distinctive part of the name; full strings differ by markup and
        # honorifics, and a false alarm here would send someone chasing a non-problem.
        tokens = [t for t in _normalise(name).split() if len(t) > 4]
        hits = sum(1 for t in tokens if t in page)
        city_ok = _normalise(city) in page if city else True

        if hits >= max(1, len(tokens) // 2) and city_ok:
            print(f"  OK           {centre.get('ern')}: {name} ({city})")
        else:
            print(f"  NOT FOUND    {centre.get('ern')}: {name} ({city}) on {url}")
            print(f"               matched {hits}/{len(tokens)} name tokens, city present: {city_ok}")
            problems += 1

    print(f"\n{problems} problem(s) across {len(centres)} recorded centre(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
