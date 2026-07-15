"""Public doctor directory — curated seed merged with latest doctor_finder workflow results."""
from __future__ import annotations

import html
import json
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any, Literal

try:
    from .config import BACKEND_DIR
    from .content_db import get_disease_by_slug, list_diseases_catalog, normalize_disease_slug
    from .doctor_geo_coords import coords_for_city_country, resolve_location
except ImportError:
    from config import BACKEND_DIR
    from content_db import get_disease_by_slug, list_diseases_catalog, normalize_disease_slug
    from doctor_geo_coords import coords_for_city_country, resolve_location

CONTENT_DOCTORS_PATH = BACKEND_DIR / "content_doctors.json"

PubmedRole = Literal[
    "research_leader",
    "research_participant",
    "case_study_author",
    "unknown",
]

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
_MIN_CATALOG_NAME_MATCH_SCORE = 45

_FINDER_DOCS_INDEX: dict[str, list[dict[str, Any]] | None] | None = None
# Version key the cached index was built at (row_count, max_finished_at) — see
# B3a. Lets any process self-invalidate when the persistent doctor_finder store
# changes, even though clear_finder_docs_index() only fires in the worker.
_FINDER_DOCS_INDEX_VERSION: tuple[int, str] | None = None
_ALL_DOCTORS_CACHE: list[dict[str, Any]] | None = None
# Finding 2: version-gate the global all-doctors cache off the same finder key,
# so the home-page global doctorCount also refreshes cross-process (not only
# per-disease counts) without a restart.
_ALL_DOCTORS_CACHE_VERSION: tuple[int, str] | None = None
_CONTENT_DOCTORS_CACHE: list[dict[str, Any]] | None = None
# DOC-5 approved contributions, cached per process alongside the finder index.
_APPROVED_SUBMISSIONS_CACHE: list[dict[str, Any]] | None = None
_APPROVED_RECS_BY_SLUG_CACHE: dict[str, list[dict[str, Any]]] | None = None
_CATALOG_CACHE_LOCK = threading.RLock()


def clear_finder_docs_index() -> None:
    """Drop cached doctor_finder rows (call after a run finishes)."""
    global _FINDER_DOCS_INDEX, _FINDER_DOCS_INDEX_VERSION
    global _ALL_DOCTORS_CACHE, _ALL_DOCTORS_CACHE_VERSION, _CONTENT_DOCTORS_CACHE
    global _APPROVED_SUBMISSIONS_CACHE, _APPROVED_RECS_BY_SLUG_CACHE
    with _CATALOG_CACHE_LOCK:
        _FINDER_DOCS_INDEX = None
        _FINDER_DOCS_INDEX_VERSION = None
        _ALL_DOCTORS_CACHE = None
        _ALL_DOCTORS_CACHE_VERSION = None
        _CONTENT_DOCTORS_CACHE = None
        _APPROVED_SUBMISSIONS_CACHE = None
        _APPROVED_RECS_BY_SLUG_CACHE = None


# Diacritics NFKD doesn't decompose (Latin letters with strokes/ligatures). Everything else
# (ą ć ę ń ó ś ź ż, accents) folds via NFKD + combining-mark strip below.
_TRANSLIT = {
    "ł": "l", "Ł": "l", "ø": "o", "Ø": "o", "đ": "d", "Đ": "d",
    "ß": "ss", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe", "ð": "d", "þ": "th",
}


def _ascii_fold(text: str) -> str:
    """Transliterate diacritics/special letters to ASCII so slugs never carry non-ASCII
    (e.g. ``Błaszyk`` → ``blaszyk``). Prevents ``%C5%82``-style URLs that 404 the profile page."""
    mapped = "".join(_TRANSLIT.get(ch, ch) for ch in text)
    decomposed = unicodedata.normalize("NFKD", mapped)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def slugify_doctor_name(display_name: str, author_key: str | None = None) -> str:
    """Stable, ASCII-only URL slug for a clinician profile."""
    if author_key:
        cleaned = _ascii_fold(author_key.replace("name:", "").replace("_", "-")).lower()
        cleaned = _SLUG_RE.sub("-", cleaned).strip("-")
        if cleaned:
            return cleaned[:64].strip("-")
    base = _ascii_fold(display_name).lower().strip()
    slug = _SLUG_RE.sub("-", base).strip("-")
    return slug[:64] if slug else "clinician"


def _role_to_pubmed_role(role: str) -> str:
    lowered = role.lower()
    if "leader" in lowered or "senior" in lowered or "consensus" in lowered:
        return "research_leader"
    if "case" in lowered:
        return "case_study_author"
    if role:
        return "research_participant"
    return "unknown"


def _name_tokens(s: str) -> set[str]:
    return set(_TOKEN_RE.findall((s or "").lower()))


def _decode_stored_text(text: str) -> str:
    """Fix legacy doctor_finder rows that stored PubMed numeric entities literally."""
    if not text or "&" not in text:
        return text
    return html.unescape(text)


def _entry_to_public_doctor(
    entry: dict[str, Any],
    *,
    diseases: list[str],
    source: str,
    execution_id: str | None = None,
) -> dict[str, Any]:
    flags = entry.get("flags") or {}
    if not isinstance(flags, dict):
        flags = {}
    evidence_summary = entry.get("evidence_summary") or {}
    if not isinstance(evidence_summary, dict):
        evidence_summary = {}
    display_name = _decode_stored_text(str(entry.get("display_name") or "Unknown"))
    author_key = entry.get("author_key")
    slug = slugify_doctor_name(display_name, str(author_key) if author_key else None)
    affiliation_raw = entry.get("affiliation")
    affiliation = (
        _decode_stored_text(str(affiliation_raw)) if affiliation_raw is not None else None
    )
    explicit_city = _decode_stored_text(str(entry.get("city") or "").strip())
    country_raw = str(entry.get("country") or "").strip().upper()
    country_iso = country_raw[:2] if len(country_raw) >= 2 and country_raw[:2].isalpha() else ""

    if explicit_city and len(country_iso) == 2:
        city, country = explicit_city, country_iso
    else:
        city, country = _parse_affiliation_location(
            str(affiliation) if affiliation else "",
            country_iso or str(entry.get("country") or ""),
        )
        if explicit_city and (not city or city == "—"):
            city = explicit_city
    _loc = resolve_location(city, country)
    if _loc is not None:
        lat, lng, _resolved_iso2 = _loc
        # Backfill a country the source record lacked (bucket B: a real city, no country) so the
        # card + country filter stay consistent with the pin the gazetteer just placed.
        if _resolved_iso2 and not (len(country) == 2 and country.isalpha()):
            country = _resolved_iso2
    else:
        lat, lng = None, None
    key_papers = entry.get("key_papers") or []
    publications = [
        {
            "pmid": str(p.get("pmid") or ""),
            "title": _decode_stored_text(str(p.get("title") or "")),
            "year": p.get("year"),
            "journal": _decode_stored_text(str(p.get("article_type") or "")),
            "position": str(p.get("author_position") or "author"),
            "meshMajor": bool(p.get("mesh_major", False)),
        }
        for p in key_papers
        if isinstance(p, dict) and p.get("pmid")
    ]
    pubmed_role = _role_to_pubmed_role(str(entry.get("role") or ""))
    # Phase 0: the PubMed role is NOT a clinical specialty. Leave ``specialty`` empty unless
    # Phase 1 specialty enrichment (NPPES) attached a verified NUCC specialty, in which case the
    # deprecated ``specialty`` display string mirrors the top canonical label. ``role``/
    # ``pubmedRole`` still carry the research axis independently.
    clinical_specialties = [
        s for s in (entry.get("clinical_specialties") or []) if isinstance(s, dict)
    ]
    specialty_display = str(clinical_specialties[0].get("labelEn") or "") if clinical_specialties else ""
    reachability = str(entry.get("reachability") or "unknown")
    # A real NPPES practice address supersedes the noisy affiliation-derived city.
    resolved_practice = entry.get("resolved_practice")
    practices: list[dict[str, Any]] = []
    if isinstance(resolved_practice, dict) and resolved_practice.get("city"):
        p_city = str(resolved_practice.get("city") or city)
        p_country = str(resolved_practice.get("country") or country)
        _p_coords = coords_for_city_country(p_city, p_country)
        p_lat, p_lng = _p_coords if _p_coords is not None else (None, None)
        p_state = str(resolved_practice.get("state") or "")
        practices = [{
            "type": str(resolved_practice.get("type") or "primary"),
            "name": str(resolved_practice.get("name") or affiliation or "Practice location"),
            "address": resolved_practice.get("address"),
            "city": p_city,
            "state": p_state,
            "country": p_country,
            "lat": p_lat,
            "lng": p_lng,
            "source": str(resolved_practice.get("source") or "nppes"),
            "confidence": str(resolved_practice.get("confidence") or "medium"),
        }]
        city, country, lat, lng = p_city, p_country, p_lat, p_lng
    return {
        "slug": slug,
        "name": display_name,
        "specialty": specialty_display,
        "clinicalSpecialties": clinical_specialties,
        "reachability": reachability,
        "practices": practices,
        "role": str(entry.get("role") or ""),
        "institution": str(affiliation or "Affiliation not listed"),
        "city": city,
        "country": country,
        "lat": lat,
        "lng": lng,
        "diseases": diseases,
        "pubmedRole": pubmed_role,
        "experienceByDisease": {d: pubmed_role for d in diseases},
        "addedVia": "pubmed",
        "score": int(round(float(entry.get("score") or 0))),
        "evidence": {
            "firstOrLastAuthorPapers": int(
                evidence_summary.get("original_papers", 0)
                + evidence_summary.get("review_papers", 0)
            ),
            "reviewPapers": int(evidence_summary.get("review_papers", 0)),
            "citesRecentGuidelines": bool(flags.get("cites_current_guidelines")),
            "activeLast2y": bool(flags.get("active_last_2y")),
            "guidelineOrConsensusCoauthor": bool(flags.get("guideline_author")),
            "runsClinicalTrial": bool(flags.get("runs_clinical_trial")),
        },
        "publications": publications,
        "bio": entry.get("ai_justification") or "",
        "publicSource": "PubMed · Doctor Finder",
        "endorsements": [],
        "contact": "form",
        "source": source,
        "executionId": execution_id,
        "identityConfidence": str(entry.get("identity_confidence") or "low"),
    }


_ROLE_PRECEDENCE: dict[str, int] = {
    "research_leader": 0,
    "case_study_author": 1,
    "research_participant": 2,
    "unknown": 3,
}

_NAME_PREFIX_RE = re.compile(
    r"^(prof\.?|professor|dr\.?|doctor|md|phd|msc|mgr)\s+",
    re.I,
)


def _canonical_name_key(display_name: str) -> str:
    """Normalize display names for matching seed rows to doctor_finder rows."""
    s = (display_name or "").strip().lower()
    s = re.sub(r"[.'`’]", " ", s)
    s = _NAME_PREFIX_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _loose_name_key(display_name: str) -> str:
    """First + last name token only, dropping middle names/initials.

    PubMed renders the same person inconsistently ("Edward Hsiao" vs "Edward C Hsiao" vs
    "Edward C. Hsiao"), which defeats the exact ``_canonical_name_key`` match and leaves a curated
    seed row un-merged next to its finder row (flagship experts appearing twice). This looser key
    collapses those variants. Used only as a SECONDARY match tier, and only when both keys have a
    real first + last token (single-token names are too collision-prone to loose-match).
    """
    canon = _canonical_name_key(display_name)
    tokens = [t for t in canon.split(" ") if t]
    if len(tokens) < 2:
        return ""
    return f"{tokens[0]} {tokens[-1]}"


def _pick_pubmed_role(a: str, b: str) -> str:
    ra = (a or "unknown").strip()
    rb = (b or "unknown").strip()
    return ra if _ROLE_PRECEDENCE.get(ra, 9) <= _ROLE_PRECEDENCE.get(rb, 9) else rb


def _merge_evidence_dicts(seed_ev: dict[str, Any], finder_ev: dict[str, Any]) -> dict[str, Any]:
    a, b = seed_ev or {}, finder_ev or {}
    return {
        "firstOrLastAuthorPapers": max(int(a.get("firstOrLastAuthorPapers") or 0), int(b.get("firstOrLastAuthorPapers") or 0)),
        "reviewPapers": max(int(a.get("reviewPapers") or 0), int(b.get("reviewPapers") or 0)),
        "citesRecentGuidelines": bool(a.get("citesRecentGuidelines")) or bool(b.get("citesRecentGuidelines")),
        "activeLast2y": bool(a.get("activeLast2y")) or bool(b.get("activeLast2y")),
        "guidelineOrConsensusCoauthor": bool(a.get("guidelineOrConsensusCoauthor"))
        or bool(b.get("guidelineOrConsensusCoauthor")),
        "runsClinicalTrial": bool(a.get("runsClinicalTrial")) or bool(b.get("runsClinicalTrial")),
    }


def _nppes_practice(row: dict[str, Any]) -> dict[str, Any] | None:
    """The row's NPPES-sourced practice (authoritative government address), if any."""
    for p in row.get("practices") or []:
        if isinstance(p, dict) and str(p.get("source") or "") == "nppes" and p.get("city"):
            return p
    return None


def _merge_publication_lists(seed_pubs: list[Any], finder_pubs: list[Any]) -> list[dict[str, Any]]:
    by_pmid: dict[str, dict[str, Any]] = {}
    for pub in (seed_pubs or []) + (finder_pubs or []):
        if not isinstance(pub, dict):
            continue
        pmid = str(pub.get("pmid") or "").strip()
        if not pmid:
            continue
        if pmid not in by_pmid:
            by_pmid[pmid] = pub
    return list(by_pmid.values())


_IDENTITY_CONF_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2}
_IDENTITY_RANK_CONF: dict[int, str] = {0: "low", 1: "medium", 2: "high"}


def _identity_conf_rank_of_row(row: dict[str, Any]) -> int:
    """Rank a public-doctor row's identity confidence (curated seed counts as verified)."""
    if str(row.get("source") or "") == "content_seed":
        return _IDENTITY_CONF_RANK["high"]
    return _IDENTITY_CONF_RANK.get(str(row.get("identityConfidence") or "low"), 0)


def _merge_public_doctor_rows(
    seed: dict[str, Any],
    finder: dict[str, Any],
    *,
    disease_slug: str,
) -> dict[str, Any]:
    """Combine curated seed with a doctor_finder hit (same person).

    Also reused for cross-disease self-merge of the same profile slug, so the
    merged identity confidence must be derived from the inputs (take the best of
    the two) rather than assumed — otherwise two name-matched finder rows would
    be falsely promoted to "verified".
    """
    slug = str(seed.get("slug") or finder.get("slug") or "").strip()
    diseases = list(dict.fromkeys([*(seed.get("diseases") or []), disease_slug, *(finder.get("diseases") or [])]))
    diseases = [str(d).strip().lower() for d in diseases if str(d).strip()]

    seed_ev = seed.get("evidence") if isinstance(seed.get("evidence"), dict) else {}
    finder_ev = finder.get("evidence") if isinstance(finder.get("evidence"), dict) else {}
    merged_ev = _merge_evidence_dicts(seed_ev, finder_ev)

    pubs = _merge_publication_lists(
        seed.get("publications") if isinstance(seed.get("publications"), list) else [],
        finder.get("publications") if isinstance(finder.get("publications"), list) else [],
    )

    seed_bio = str(seed.get("bio") or "")
    finder_bio = str(finder.get("bio") or "")
    bio = finder_bio if len(finder_bio) > len(seed_bio) else seed_bio

    seed_inst = str(seed.get("institution") or "").strip()
    finder_inst = str(finder.get("institution") or "").strip()
    institution = finder_inst if len(finder_inst) > len(seed_inst) else (seed_inst or finder_inst)

    # Prefer a clean, authoritative location. An NPPES-sourced practice (real government address)
    # beats a PubMed-affiliation guess, and a clean ISO2 country beats a US-state-abbrev artifact
    # ("MD") or "—". This stops the dedup merge from regressing "Washington, US" to "WASHINGTON, MD".
    seed_pr = _nppes_practice(seed)
    finder_pr = _nppes_practice(finder)
    authoritative = seed_pr or finder_pr

    seed_city = str(seed.get("city") or "").strip()
    finder_city = str(finder.get("city") or "").strip()
    seed_country = str(seed.get("country") or "").strip()
    finder_country = str(finder.get("country") or "").strip()

    if authoritative:
        city = str(authoritative.get("city") or "").strip() or finder_city or seed_city or "—"
        country = str(authoritative.get("country") or "").strip() or "—"
    else:
        city = finder_city if seed_city in {"", "—"} else seed_city
        if not city:
            city = finder_city or seed_city or "—"
        # A clean 2-letter ISO country wins over a state-abbrev/"—" bucket.
        cc = [c for c in (seed_country, finder_country) if _country_bucket(c)]
        country = cc[0] if cc else (finder_country or seed_country or "—")

    # Preserve a precise (seed-curated) coordinate, else the finder's; when neither knows the
    # location keep it None so the map skips the pin instead of dropping it onto null island (0,0).
    _lat_val = seed.get("lat") or finder.get("lat")
    _lng_val = seed.get("lng") or finder.get("lng")
    lat = float(_lat_val) if _lat_val is not None else None
    lng = float(_lng_val) if _lng_val is not None else None

    endorsements: list[str] = []
    for src in (seed.get("endorsements"), finder.get("endorsements")):
        if isinstance(src, list):
            for e in src:
                t = str(e).strip()
                if t and t not in endorsements:
                    endorsements.append(t)

    ps_parts: list[str] = []
    for p in (str(seed.get("publicSource") or "").strip(), str(finder.get("publicSource") or "").strip()):
        if p and p not in ps_parts:
            ps_parts.append(p)
    public_source = " · ".join(ps_parts) if ps_parts else str(finder.get("publicSource") or "")

    score = max(int(seed.get("score") or 0), int(finder.get("score") or 0))
    # Curated seed specialty WINS: the finder has no verified clinical-specialty source (Phase 0
    # leaves its ``specialty`` empty), so a name-matched finder hit must never overwrite a
    # hand-curated clinical specialty (regression: Riminucci/Appelman-Dijkstra lost theirs).
    specialty = str(seed.get("specialty") or finder.get("specialty") or "")
    role = str(finder.get("role") or seed.get("role") or "")

    # draft9 directory fields: seed (curated) wins, finder fills gaps. parentRecs/rodo only
    # come from the curated seed today; experienceByDisease merges per-disease (seed overrides).
    experience_by_disease = {
        **(finder.get("experienceByDisease") if isinstance(finder.get("experienceByDisease"), dict) else {}),
        **(seed.get("experienceByDisease") if isinstance(seed.get("experienceByDisease"), dict) else {}),
    }
    # An NPPES practice (authoritative address) wins; else curated seed practices; else finder's.
    if authoritative is not None:
        practices = [authoritative]
    else:
        practices = (
            seed.get("practices")
            if isinstance(seed.get("practices"), list) and seed.get("practices")
            else finder.get("practices")
        ) or []
    # Dedup like publications/endorsements above: the global directory self-merges the same
    # seed row once per disease, so a plain concat would multiply each recommendation.
    parent_recs: list[dict[str, Any]] = []
    seen_recs: set[tuple[str, str, str]] = set()
    for rec in [
        *(seed.get("parentRecs") if isinstance(seed.get("parentRecs"), list) else []),
        *(finder.get("parentRecs") if isinstance(finder.get("parentRecs"), list) else []),
    ]:
        if not isinstance(rec, dict):
            continue
        key = (str(rec.get("text") or ""), str(rec.get("by") or ""), str(rec.get("date") or ""))
        if key in seen_recs:
            continue
        seen_recs.add(key)
        parent_recs.append(rec)
    added_via = str(seed.get("addedVia") or finder.get("addedVia") or "pubmed")
    rodo = seed.get("rodo") or finder.get("rodo")
    review_status = seed.get("reviewStatus") or finder.get("reviewStatus")

    # Clinical specialties: union seed (curated) + finder (NPPES), deduped by canonical code;
    # curated entries listed first so a hand-verified specialty wins the display slot.
    clinical_specialties: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for s in [
        *(seed.get("clinicalSpecialties") if isinstance(seed.get("clinicalSpecialties"), list) else []),
        *(finder.get("clinicalSpecialties") if isinstance(finder.get("clinicalSpecialties"), list) else []),
    ]:
        if not isinstance(s, dict):
            continue
        code = str(s.get("canonicalCode") or "")
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        clinical_specialties.append(s)
    # Availability: prefer the strongest known signal, but expert_reachable must never be lost.
    _reach_rank = {"sees_patients": 2, "expert_reachable": 1, "unknown": 0}
    reachability = max(
        (str(seed.get("reachability") or "unknown"), str(finder.get("reachability") or "unknown")),
        key=lambda r: _reach_rank.get(r, 0),
    )

    return {
        "slug": slug,
        "name": str(seed.get("name") or finder.get("name") or "Unknown"),
        "specialty": specialty,
        "clinicalSpecialties": clinical_specialties,
        "reachability": reachability,
        "role": role,
        "institution": institution,
        "city": city,
        "country": country,
        "lat": lat,
        "lng": lng,
        "diseases": diseases,
        "pubmedRole": _pick_pubmed_role(str(seed.get("pubmedRole") or ""), str(finder.get("pubmedRole") or "")),
        "score": score,
        "evidence": merged_ev,
        "publications": pubs,
        "bio": bio,
        "publicSource": public_source,
        "endorsements": endorsements,
        "contact": str(seed.get("contact") or finder.get("contact") or "form"),
        "source": "merged",
        "executionId": finder.get("executionId"),
        # Best of the two inputs: a curated seed verifies identity (high), but two
        # name-matched finder rows stay name-matched — never falsely "verified".
        "identityConfidence": _IDENTITY_RANK_CONF[
            max(_identity_conf_rank_of_row(seed), _identity_conf_rank_of_row(finder))
        ],
        "practices": practices,
        "experienceByDisease": experience_by_disease,
        "addedVia": added_via,
        "rodo": rodo,
        "parentRecs": parent_recs,
        "reviewStatus": review_status,
    }


def _finder_index_matching_seed(seed: dict[str, Any], finder_docs: list[dict[str, Any]], used: set[int]) -> int | None:
    sslug = str(seed.get("slug") or "").strip().lower()
    snk = _canonical_name_key(str(seed.get("name") or ""))
    slk = _loose_name_key(str(seed.get("name") or ""))
    for i, f in enumerate(finder_docs):
        if i in used:
            continue
        if sslug and str(f.get("slug") or "").strip().lower() == sslug:
            return i
    for i, f in enumerate(finder_docs):
        if i in used:
            continue
        if snk and _canonical_name_key(str(f.get("name") or "")) == snk:
            return i
    # Secondary tier: collapse middle-initial variants ("Edward Hsiao" ~ "Edward C Hsiao") so a
    # curated seed expert merges with their finder row instead of appearing twice.
    for i, f in enumerate(finder_docs):
        if i in used:
            continue
        if slk and _loose_name_key(str(f.get("name") or "")) == slk:
            return i
    return None


def _ensure_experience_key(row: dict[str, Any], disease_slug: str) -> None:
    """Make sure ``row["experienceByDisease"]`` has ``disease_slug`` (default: the row's pubmedRole).

    Mutates the local ``row`` copy only. Called whenever a disease is appended to ``row["diseases"]``
    so per-disease tiers stay complete (consumer still has tierForDisease fallback, but data should
    not depend on it).
    """
    if not disease_slug:
        return
    experience = row.get("experienceByDisease")
    if not isinstance(experience, dict):
        experience = {}
    else:
        experience = dict(experience)
    experience.setdefault(disease_slug, str(row.get("pubmedRole") or "unknown"))
    row["experienceByDisease"] = experience


# US state / territory abbreviations that the finder geo step sometimes mis-stores in the country
# field (e.g. "MD" for Maryland). Treated as "country unknown" for dedup so a state-vs-ISO2 quirk
# doesn't keep the same person split.
_US_STATE_ABBREVS = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC",
})


def _country_bucket(country: str) -> str:
    """Normalize a country value for dedup: dirty/unknown (empty, "—", a US state abbrev) → ""."""
    c = (country or "").strip().upper()
    if not c or c == "—" or c in _US_STATE_ABBREVS:
        return ""
    return c[:2] if len(c) >= 2 and c[:2].isalpha() else ""


def _dedup_finder_docs(finder_docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse finder rows that are the same real person split across author clusters.

    PubMed disambiguation fragments one person into several ``author_key`` clusters (ORCID-keyed +
    initials-keyed), so "Michael T Collins" / "Alison Boyce" appeared 2–3× in the public list. We
    merge rows sharing the same loose name key (first+last), UNLESS both carry a real, *different*
    ISO country (then they're probably distinct same-surname people). The finder's geo step often
    mis-stores a US state abbrev ("MD") or "—" as the country, so those count as unknown and never
    block a merge. Single-token names never loose-merge (too collision-prone).
    """
    order: list[str] = []
    by_key: dict[str, dict[str, Any]] = {}
    # Track the known country for each merged bucket to guard against fusing distinct people.
    key_country: dict[str, str] = {}

    for f in finder_docs:
        if not isinstance(f, dict):
            continue
        slug = str(f.get("slug") or "").strip().lower()
        loose = _loose_name_key(str(f.get("name") or ""))
        cbucket = _country_bucket(str(f.get("country") or ""))

        key: str | None = None
        if loose:
            # Reuse an existing loose-name bucket if country is compatible (one side unknown, or
            # both the same known country).
            cand = f"name:{loose}"
            existing_c = key_country.get(cand)
            if cand in by_key and (not existing_c or not cbucket or existing_c == cbucket):
                key = cand
            elif cand not in by_key:
                key = cand
        if key is None:
            # Distinct known country on a same-name row, or no usable loose name → keep standalone
            # (fall back to slug identity so identical slugs still collapse).
            key = f"slug:{slug}" if slug else f"row:{len(order)}"

        if key in by_key:
            by_key[key] = _merge_public_doctor_rows(by_key[key], f, disease_slug="")
            if cbucket and not key_country.get(key):
                key_country[key] = cbucket
        else:
            by_key[key] = f
            key_country[key] = cbucket
            order.append(key)
    return [by_key[k] for k in order]


def _merge_seed_and_finder_docs(
    disease_slug: str,
    seeded: list[dict[str, Any]],
    finder_docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Curated seed + workflow hits: match by slug or normalized name; append unmatched finder rows."""
    finder_docs = _dedup_finder_docs(finder_docs)
    used_finder: set[int] = set()
    out: list[dict[str, Any]] = []

    for seed in seeded:
        if not isinstance(seed, dict):
            continue
        j = _finder_index_matching_seed(seed, finder_docs, used_finder)
        if j is None:
            row = dict(seed)
            row.setdefault("diseases", [])
            if disease_slug not in (row.get("diseases") or []):
                row["diseases"] = [*list(row.get("diseases") or []), disease_slug]
            _ensure_experience_key(row, disease_slug)
            out.append(row)
            continue
        used_finder.add(j)
        out.append(_merge_public_doctor_rows(seed, finder_docs[j], disease_slug=disease_slug))

    for i, f in enumerate(finder_docs):
        if i in used_finder or not isinstance(f, dict):
            continue
        row = dict(f)
        row["diseases"] = list(dict.fromkeys([*(row.get("diseases") or []), disease_slug]))
        _ensure_experience_key(row, disease_slug)
        out.append(row)

    out.sort(key=lambda d: -int(d.get("score") or 0))
    return out


def _parse_affiliation_location(affiliation: str, country_code: str) -> tuple[str, str]:
    country = (country_code or "—").upper()[:2] if country_code else "—"
    if "·" in affiliation:
        parts = [p.strip() for p in affiliation.split("·") if p.strip()]
        if len(parts) >= 2:
            city_guess = parts[-1].split(",")[0].strip()
            if len(city_guess) <= 40:
                return city_guess, country
    try:
        from .doctor_geo_coords import _CITY_COORDS_LOWER
    except ImportError:
        from doctor_geo_coords import _CITY_COORDS_LOWER

    for city_name in _CITY_COORDS_LOWER:
        if city_name in affiliation.lower():
            return city_name.title(), country
    return "—", country


def _load_content_doctors_file() -> list[dict[str, Any]]:
    """Load curated doctors seed once per process (invalidated with finder index)."""
    global _CONTENT_DOCTORS_CACHE
    with _CATALOG_CACHE_LOCK:
        if _CONTENT_DOCTORS_CACHE is not None:
            return _CONTENT_DOCTORS_CACHE
        path = Path(CONTENT_DOCTORS_PATH)
        if not path.exists():
            _CONTENT_DOCTORS_CACHE = []
            return _CONTENT_DOCTORS_CACHE
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("doctors", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            _CONTENT_DOCTORS_CACHE = []
            return _CONTENT_DOCTORS_CACHE
        _CONTENT_DOCTORS_CACHE = [r for r in rows if isinstance(r, dict)]
        return _CONTENT_DOCTORS_CACHE


# ---------------------------------------------------------------------------
# DOC-5 — approved parent contributions mixed into the public catalogue.
#
# Pending/rejected contributions are NEVER public. Approved doctor submissions
# enter as standalone ``addedVia:"parent"`` rows that do NOT merge with finder
# hits (separate line — manual merge is post-V1). Approved parent recommendations
# attach to whichever doctor (catalogue, seed, or parent-added) carries the
# recommended slug, and ``parentRecCount`` syncs through the existing
# ``PublicDoctorResponse`` validator.
# ---------------------------------------------------------------------------


def _load_approved_contributions() -> tuple[
    list[dict[str, Any]], dict[str, list[dict[str, Any]]]
]:
    """Read approved submissions + recs once per process (best-effort, never raises).

    Returns ``(approved_submission_doctor_rows, approved_recs_by_doctor_slug)``.
    A missing/unconfigured DB yields empty results so the public read path keeps
    working with seed + finder data alone.
    """
    global _APPROVED_SUBMISSIONS_CACHE, _APPROVED_RECS_BY_SLUG_CACHE
    with _CATALOG_CACHE_LOCK:
        if (
            _APPROVED_SUBMISSIONS_CACHE is not None
            and _APPROVED_RECS_BY_SLUG_CACHE is not None
        ):
            return _APPROVED_SUBMISSIONS_CACHE, _APPROVED_RECS_BY_SLUG_CACHE

        submissions: list[dict[str, Any]] = []
        recs_by_slug: dict[str, list[dict[str, Any]]] = {}
        try:
            from .doctor_contributions.models import ReviewStatus
            from .doctor_contributions.repository import SqlaDoctorContributionsRepo
        except ImportError:  # pragma: no cover - flat-layout import shim
            from doctor_contributions.models import ReviewStatus  # type: ignore[no-redef]
            from doctor_contributions.repository import (  # type: ignore[no-redef]
                SqlaDoctorContributionsRepo,
            )

        try:
            repo = SqlaDoctorContributionsRepo()
            for s in repo.list_submissions(review_status=ReviewStatus.APPROVED):
                submissions.append(_submission_to_public_doctor(s))
            for r in repo.list_parent_recs(review_status=ReviewStatus.APPROVED):
                recs_by_slug.setdefault(r.doctor_slug, []).append(
                    {
                        "text": r.text,
                        "by": (r.relation.value if r.relation else "parent"),
                        "region": r.region or "",
                        "date": (r.created_at or "")[:10],
                    }
                )
        except Exception:  # noqa: BLE001 - no DB / unconfigured engine -> seed+finder only
            submissions = []
            recs_by_slug = {}

        _APPROVED_SUBMISSIONS_CACHE = submissions
        _APPROVED_RECS_BY_SLUG_CACHE = recs_by_slug
        return submissions, recs_by_slug


def _submission_to_public_doctor(submission: Any) -> dict[str, Any]:
    """Map an approved :class:`DoctorSubmission` to a public-doctor row."""
    city = str(getattr(submission, "city", "") or "").strip() or "—"
    country = str(getattr(submission, "country", "") or "").strip().upper()[:2] or "—"
    _coords = coords_for_city_country(city, country)
    lat, lng = _coords if _coords is not None else (None, None)
    disease_slug = str(getattr(submission, "disease_slug", "") or "").strip().lower()
    diseases = [disease_slug] if disease_slug else []
    return {
        "slug": str(submission.slug),
        "name": str(submission.name),
        "specialty": str(getattr(submission, "specialty", "") or "Clinician"),
        "role": str(getattr(submission, "specialty", "") or ""),
        "institution": str(getattr(submission, "institution", "") or "Affiliation not listed"),
        "city": city,
        "country": country,
        "lat": lat,
        "lng": lng,
        "diseases": diseases,
        "pubmedRole": "unknown",
        "experienceByDisease": {d: "unknown" for d in diseases},
        "addedVia": "parent",
        "score": 0,
        "evidence": {
            "firstOrLastAuthorPapers": 0,
            "reviewPapers": 0,
            "citesRecentGuidelines": False,
            "activeLast2y": False,
            "guidelineOrConsensusCoauthor": False,
        },
        "publications": [],
        "bio": str(getattr(submission, "note", "") or ""),
        "publicSource": "Family submission",
        "endorsements": [],
        "contact": "form",
        "source": "content_seed",
        "executionId": None,
        "parentRecs": [],
        "reviewStatus": None,
    }


def _apply_approved_recs(row: dict[str, Any]) -> dict[str, Any]:
    """Append approved parent recs (by slug) to a doctor row, deduped by content."""
    _submissions, recs_by_slug = _load_approved_contributions()
    slug = str(row.get("slug") or "").strip().lower()
    extra = recs_by_slug.get(slug)
    if not extra:
        return row
    merged = list(row.get("parentRecs") or [])
    seen = {
        (str(r.get("text") or ""), str(r.get("by") or ""), str(r.get("date") or ""))
        for r in merged
        if isinstance(r, dict)
    }
    for rec in extra:
        key = (str(rec.get("text") or ""), str(rec.get("by") or ""), str(rec.get("date") or ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(rec)
    out = dict(row)
    out["parentRecs"] = merged
    return out


def _approved_submission_rows_for_disease(normalized: str) -> list[dict[str, Any]]:
    """Approved parent-added doctors that list ``normalized`` (recs applied)."""
    submissions, _recs = _load_approved_contributions()
    rows: list[dict[str, Any]] = []
    for sub in submissions:
        if normalized in (sub.get("diseases") or []):
            rows.append(_apply_approved_recs(sub))
    return rows


def _disease_slug_for_name(disease_name: str) -> str | None:
    """Map doctor_finder free-text disease input to a catalog slug (DB + keyword heuristics)."""
    lowered = disease_name.strip().lower()
    if not lowered:
        return None
    aliases = {
        "fd": ("fibrous dysplasia", "fd", "dysplasia"),
        "mas": ("mccune", "mc cune", "albright", "mas"),
        "noonan": ("noonan",),
    }
    for slug, parts in aliases.items():
        if any(part in lowered for part in parts):
            return slug

    compact = lowered.replace(" ", "-").replace("/", "-")
    for candidate in (lowered, compact, compact.replace("--", "-")):
        ns = normalize_disease_slug(candidate)
        if ns and get_disease_by_slug(ns) is not None:
            return ns

    tokens = _name_tokens(lowered)
    best_slug: str | None = None
    best_score = 0
    try:
        catalog = list_diseases_catalog()
    except Exception:
        catalog = []
    for d in catalog:
        slug = str(d.get("slug") or "").strip().lower()
        if not slug:
            continue
        name_l = str(d.get("name") or "").strip().lower()
        short_l = str(d.get("nameShort") or "").strip().lower()
        gene_l = str(d.get("gene") or "").strip().lower()
        score = 0
        if slug == lowered:
            score = 5000
        elif slug in tokens and len(slug) >= 2:
            score = 1500
        elif short_l and short_l in tokens and len(short_l) >= 2:
            score = 1200
        elif name_l and name_l in lowered and len(name_l) >= 8:
            score = 800 + min(len(name_l), 120)
        elif name_l and lowered in name_l and len(lowered) >= 6:
            score = 700 + min(len(lowered), 120)
        elif short_l and len(short_l) >= 3 and (lowered.startswith(short_l) or short_l in lowered):
            score = 600
        elif gene_l and len(gene_l) >= 3 and gene_l.lower() in tokens:
            score = 200
        if score > best_score:
            best_score = score
            best_slug = slug
    if best_slug is not None and best_score >= _MIN_CATALOG_NAME_MATCH_SCORE:
        return best_slug

    row = get_disease_by_slug(lowered.replace(" ", "-"))
    if row is not None:
        return str(row["slug"])
    return None


def catalog_slug_for_finder_input(disease_name: str) -> str | None:
    """Map doctor_finder disease input to content catalog slug (for DB persistence)."""
    return _disease_slug_for_name(disease_name)


def _public_doctors_from_finder_report(
    disease_slug: str,
    report: dict[str, Any],
    *,
    execution_id: str | None,
) -> list[dict[str, Any]] | None:
    authors = report.get("top_authors") or []
    if not isinstance(authors, list) or not authors:
        return None
    return [
        _entry_to_public_doctor(
            entry if isinstance(entry, dict) else {},
            diseases=[disease_slug],
            source="doctor_finder",
            execution_id=execution_id or None,
        )
        for entry in authors
        if isinstance(entry, dict)
    ]


def _build_finder_docs_index() -> dict[str, list[dict[str, Any]] | None]:
    """One pass over the PERSISTENT doctor_finder store (cached per process).

    Reads ONLY ``doctor_finder_run_results`` (the durable store). With the
    dedicated research worker (plan §4.5) the in-memory ``DOCTOR_FINDER_RUNS``
    map lives in a different process and never holds the worker's runs, so
    merging it here is both useless and the source of the 2026-06-24 500-error
    class (comparing two sources with different key shapes). The persistent
    store is the single source of truth for the catalog.
    """
    try:
        from .doctor_finder_store import load_successful_reports_for_catalog_index
    except ImportError:
        from doctor_finder_store import load_successful_reports_for_catalog_index

    index: dict[str, list[dict[str, Any]] | None] = {}
    for slug, (eid, report, _started) in load_successful_reports_for_catalog_index().items():
        index[slug] = _public_doctors_from_finder_report(
            slug,
            report,
            execution_id=eid or None,
        )
    return index


def _finder_docs_index() -> dict[str, list[dict[str, Any]] | None]:
    """Return the cached persistent finder index, rebuilding it when the DB moved.

    B3a: the index is a process-lifetime memoized global. ``clear_finder_docs_index``
    only fires in the worker, so the read-serving process would otherwise pin a
    stale index (``doctorsCount=0`` for a freshly bootstrapped disease) until a
    restart. We compare a cheap DB version key (row count + newest ``finished_at``)
    and rebuild in ANY process when it changes. If the probe fails we fall back to
    plain memoisation (rebuild only when unset) rather than thrash.
    """
    global _FINDER_DOCS_INDEX, _FINDER_DOCS_INDEX_VERSION
    try:
        from .doctor_finder_store import finder_results_version_key
    except ImportError:
        from doctor_finder_store import finder_results_version_key

    version = finder_results_version_key()
    with _CATALOG_CACHE_LOCK:
        stale = version is not None and version != _FINDER_DOCS_INDEX_VERSION
        if _FINDER_DOCS_INDEX is None or stale:
            _FINDER_DOCS_INDEX = _build_finder_docs_index()
            _FINDER_DOCS_INDEX_VERSION = version
        return _FINDER_DOCS_INDEX


def _merged_doctors_for_catalog_slug(
    normalized: str,
    finder_index: dict[str, list[dict[str, Any]] | None],
    *,
    seeded_docs: list[dict[str, Any]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Merge seed file + doctor_finder hits for one catalog disease slug."""
    doctors_seed = seeded_docs if seeded_docs is not None else _load_content_doctors_file()
    seeded = [
        doc
        for doc in doctors_seed
        if normalized in (doc.get("diseases") or [])
    ]
    live = finder_index.get(normalized)
    # DOC-5: approved parent-added doctors are a separate line — they do NOT merge
    # with finder hits — appended after the seed/finder result.
    parent_added = _approved_submission_rows_for_disease(normalized)

    if live and seeded:
        merged = _merge_seed_and_finder_docs(normalized, seeded, live)
        merged = [_apply_approved_recs(d) for d in merged]
        return "merged", merged + parent_added
    if live:
        # Dedup finder-only rows too (same person split across author clusters).
        live_with_recs = [_apply_approved_recs(d) for d in _dedup_finder_docs(live)]
        return "doctor_finder", live_with_recs + parent_added
    if seeded:
        seeded_with_recs = [_apply_approved_recs(d) for d in seeded]
        return "content_seed", seeded_with_recs + parent_added
    if parent_added:
        return "content_seed", parent_added
    return "none", []


def _doctors_from_live_doctor_finder(disease_slug: str) -> list[dict[str, Any]] | None:
    normalized = normalize_disease_slug(disease_slug)
    if normalized is None:
        return None
    return _finder_docs_index().get(normalized)


def get_doctors_for_disease(disease_slug: str) -> dict[str, Any]:
    """Doctors for a disease: merge latest doctor_finder with curated seed when both exist."""
    normalized = normalize_disease_slug(disease_slug)
    if normalized is None:
        return {"diseaseSlug": disease_slug, "source": "none", "doctors": []}

    source, doctors = _merged_doctors_for_catalog_slug(normalized, _finder_docs_index())
    return {"diseaseSlug": normalized, "source": source, "doctors": doctors}


def effective_public_doctor_count_for_disease(disease_slug: str) -> int:
    """Public directory size for one disease (seed + merged doctor_finder when present)."""
    normalized = normalize_disease_slug(disease_slug)
    if normalized is None:
        return 0
    counts = public_doctor_counts_by_slug([normalized])
    return counts.get(normalized, 0)


def public_doctor_counts_by_slug(slugs: list[str] | tuple[str, ...]) -> dict[str, int]:
    """Live public doctor counts for many catalog slugs in one pass.

    Used by GET /api/diseases so listing the catalog does not re-read the seed
    file and rebuild the finder index once per disease row.
    """
    finder_index = _finder_docs_index()
    seeded_docs = _load_content_doctors_file()
    counts: dict[str, int] = {}
    for raw in slugs:
        normalized = normalize_disease_slug(str(raw or ""))
        if normalized is None or normalized in counts:
            continue
        _src, doctors = _merged_doctors_for_catalog_slug(
            normalized,
            finder_index,
            seeded_docs=seeded_docs,
        )
        counts[normalized] = len(doctors)
    return counts


def total_distinct_public_doctor_profiles() -> int:
    """Distinct specialist profile slugs across all diseases (union for home-page stats)."""
    return len(list_all_doctors())


def _merge_global_doctor_entries(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Combine the same profile slug when listed under multiple diseases."""
    return _merge_public_doctor_rows(a, b, disease_slug="")


def list_all_doctors() -> list[dict[str, Any]]:
    """All doctors: seed file + per-disease doctor_finder merge, deduped by slug."""
    global _ALL_DOCTORS_CACHE, _ALL_DOCTORS_CACHE_VERSION
    try:
        from .doctor_finder_store import finder_results_version_key
    except ImportError:
        from doctor_finder_store import finder_results_version_key
    version = finder_results_version_key()
    with _CATALOG_CACHE_LOCK:
        stale = version is not None and version != _ALL_DOCTORS_CACHE_VERSION
        if _ALL_DOCTORS_CACHE is not None and not stale:
            return _ALL_DOCTORS_CACHE

        by_slug: dict[str, dict[str, Any]] = {}
        for doc in _load_content_doctors_file():
            if not isinstance(doc, dict):
                continue
            key = str(doc.get("slug") or "").strip().lower()
            if key:
                by_slug[key] = doc

        finder_index = _finder_docs_index()
        catalog_slugs: set[str] = set(finder_index.keys())

        try:
            rows = list_diseases_catalog()
        except Exception:
            rows = []
        for row in rows:
            normalized = normalize_disease_slug(str(row.get("slug") or "").strip())
            if normalized:
                catalog_slugs.add(normalized)

        for doc in by_slug.values():
            for disease in doc.get("diseases") or []:
                dslug = str(disease).strip().lower()
                if dslug:
                    catalog_slugs.add(dslug)

        for normalized in catalog_slugs:
            source, doctors = _merged_doctors_for_catalog_slug(normalized, finder_index)
            if source == "none":
                continue
            for doc in doctors:
                if not isinstance(doc, dict):
                    continue
                key = str(doc.get("slug") or "").strip().lower()
                if not key:
                    continue
                if key not in by_slug:
                    by_slug[key] = doc
                else:
                    by_slug[key] = _merge_global_doctor_entries(by_slug[key], doc)

        # DOC-5: ensure every approved parent-added doctor appears (even one with
        # no disease slug, which no per-disease pass would have surfaced).
        approved_subs, _recs = _load_approved_contributions()
        for sub in approved_subs:
            key = str(sub.get("slug") or "").strip().lower()
            if not key or key in by_slug:
                continue
            by_slug[key] = sub

        # DOC-5: apply approved parent recs to every row (seed-file rows that
        # carry no disease never went through the per-disease merge above).
        _ALL_DOCTORS_CACHE = [_apply_approved_recs(doc) for doc in by_slug.values()]
        _ALL_DOCTORS_CACHE_VERSION = version
        return _ALL_DOCTORS_CACHE


def get_doctor_by_slug(slug: str) -> dict[str, Any] | None:
    """Single doctor profile from merged catalog."""
    trimmed = slug.strip().lower()
    if not trimmed:
        return None
    return next((doc for doc in list_all_doctors() if doc.get("slug") == trimmed), None)
