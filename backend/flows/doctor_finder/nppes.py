"""NPPES (NPI Registry) client — clinical specialty + real practice address for US physicians.

Public, free, no-auth JSON API: https://npiregistry.cms.hhs.gov/api/?version=2.1
It returns each provider's NUCC taxonomy code(s) (our canonical spine) and a LOCATION address,
so it fixes both the missing-specialty axis AND the "state-abbrev-as-city" geo bug in one pass.

The make-or-break is IDENTITY MATCHING: a bare last-name search returns many unrelated people
(e.g. "Alison Boyce" -> nurse, massage therapist, family medicine, pediatric endocrinologist).
Attaching the wrong person's specialty to an FD scientist is the worst failure mode, so this
module is deliberately conservative: it only returns a specialty when it can pick ONE plausible
physician with reasonable confidence; otherwise it returns None (better empty than wrong).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx

log = logging.getLogger(__name__)

NPPES_API_URL = "https://npiregistry.cms.hhs.gov/api/"
NPPES_TIMEOUT_SEC = 12.0
NPPES_MAX_RESULTS = 20

# NUCC groupings that are actually physicians / clinicians a family would "book". Used to reject
# obvious non-matches (Home Health Aide, Massage Therapist, Physician *Assistant*, ...) when
# disambiguating by name only. NOTE: matching "physician" as a substring is wrong — it also hits
# "Physician Assistants & Advanced Practice Nursing Providers". Match the real physician grouping
# tokens instead.
_PHYSICIAN_GROUPINGS = (
    "allopathic",  # "Allopathic & Osteopathic Physicians"
    "osteopathic",
    "dental",  # "Dental Providers"
    "podiatric",  # "Podiatric Medicine & Surgery Providers"
)

_WORD_RE = re.compile(r"[a-z]+")


@dataclass(frozen=True)
class NppesMatch:
    npi: str
    first_name: str
    last_name: str
    taxonomy_code: str
    taxonomy_desc: str
    city: str = ""
    state: str = ""
    postal: str = ""
    address_1: str = ""
    org_name: str = ""
    # "high" when name + state uniquely identify a physician; "medium" when name+state match a
    # single physician but we lacked a state to fully confirm; never returned below that.
    confidence: str = "medium"
    other_candidates: int = 0


@dataclass
class NppesStats:
    queried: int = 0
    matched: int = 0
    ambiguous: int = 0
    no_result: int = 0
    errors: int = 0
    detail: list[str] = field(default_factory=list)


def _first_initial(s: str) -> str:
    s = (s or "").strip()
    return s[0].lower() if s else ""


def _is_physicianish(grouping: str) -> bool:
    g = (grouping or "").lower()
    return any(tok in g for tok in _PHYSICIAN_GROUPINGS)


def _primary_taxonomy(result: dict) -> dict | None:
    taxes = result.get("taxonomies") or []
    if not isinstance(taxes, list) or not taxes:
        return None
    primary = [t for t in taxes if isinstance(t, dict) and t.get("primary")]
    chosen = primary[0] if primary else next((t for t in taxes if isinstance(t, dict)), None)
    return chosen


def _location_address(result: dict) -> dict:
    addrs = result.get("addresses") or []
    if not isinstance(addrs, list):
        return {}
    loc = [a for a in addrs if isinstance(a, dict) and a.get("address_purpose") == "LOCATION"]
    if loc:
        return loc[0]
    return next((a for a in addrs if isinstance(a, dict)), {})


def _match_from_result(result: dict, *, confidence: str, others: int) -> NppesMatch | None:
    basic = result.get("basic") or {}
    tax = _primary_taxonomy(result)
    if not tax:
        return None
    code = str(tax.get("code") or "").strip()
    desc = str(tax.get("desc") or "").strip()
    if not code:
        return None
    addr = _location_address(result)
    return NppesMatch(
        npi=str(result.get("number") or ""),
        first_name=str(basic.get("first_name") or "").strip(),
        last_name=str(basic.get("last_name") or "").strip(),
        taxonomy_code=code,
        taxonomy_desc=desc,
        city=str(addr.get("city") or "").strip(),
        state=str(addr.get("state") or "").strip(),
        postal=str(addr.get("postal_code") or "").strip()[:5],
        address_1=str(addr.get("address_1") or "").strip(),
        org_name=str(basic.get("organization_name") or "").strip(),
        confidence=confidence,
        other_candidates=others,
    )


def _pick(results: list[dict], *, first_initial: str, have_state: bool) -> NppesMatch | None:
    """Disambiguate NPPES results into at most one confident physician match, else None.

    Rules (conservative):
    - keep only NPI-1 (individual) results whose first initial matches the sought author and whose
      grouping is physician-ish;
    - if exactly one survives -> match (high when a state was used to filter, else medium);
    - if several physician-ish survive -> ambiguous -> None (never guess a specialty).
    """
    individuals = [
        r for r in results
        if isinstance(r, dict) and str(r.get("enumeration_type") or "") == "NPI-1"
    ]
    plausible: list[dict] = []
    for r in individuals:
        basic = r.get("basic") or {}
        if first_initial and _first_initial(str(basic.get("first_name") or "")) != first_initial:
            continue
        tax = _primary_taxonomy(r)
        grouping = str((tax or {}).get("grouping") or "")
        if not _is_physicianish(grouping):
            continue
        plausible.append(r)

    if len(plausible) == 1:
        conf = "high" if have_state else "medium"
        return _match_from_result(plausible[0], confidence=conf, others=0)
    if len(plausible) > 1:
        # Ambiguous even after the physician + initial filter — refuse to guess.
        return None
    return None


async def lookup_us_specialty(
    *,
    last_name: str,
    first_name: str = "",
    state: str = "",
    client: httpx.AsyncClient | None = None,
) -> NppesMatch | None:
    """Look up a single US physician's NUCC specialty + practice address, or None if unsure.

    Passing ``state`` (2-letter USPS) is strongly recommended — it both narrows results and lifts
    a successful single match to ``high`` confidence. Returns None on any network error, no
    result, or ambiguity (the caller records "unverified" rather than a wrong specialty).
    """
    ln = (last_name or "").strip()
    if not ln:
        return None
    params: dict[str, str] = {
        "version": "2.1",
        "last_name": ln,
        "limit": str(NPPES_MAX_RESULTS),
        "enumeration_type": "NPI-1",
    }
    if first_name.strip():
        params["first_name"] = first_name.strip()
    st = (state or "").strip().upper()
    have_state = len(st) == 2 and st.isalpha()
    if have_state:
        params["state"] = st

    async def _do(c: httpx.AsyncClient) -> NppesMatch | None:
        try:
            resp = await c.get(NPPES_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001 - any failure => no assignment (safe)
            log.debug("nppes lookup failed last_name=%s: %s", ln, exc)
            return None
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            return None
        return _pick(results, first_initial=_first_initial(first_name), have_state=have_state)

    if client is not None:
        return await _do(client)
    async with httpx.AsyncClient(timeout=NPPES_TIMEOUT_SEC) as c:
        return await _do(c)
