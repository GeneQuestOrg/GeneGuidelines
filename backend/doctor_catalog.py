"""Public doctor directory — curated seed merged with latest doctor_finder workflow results."""
from __future__ import annotations

import html
import json
import re
import threading
from pathlib import Path
from typing import Any, Literal

try:
    from .config import BACKEND_DIR
    from .content_db import get_disease_by_slug, list_diseases, list_diseases_catalog, normalize_disease_slug
    from .doctor_geo_coords import coords_for_city_country
except ImportError:
    from config import BACKEND_DIR
    from content_db import get_disease_by_slug, list_diseases, list_diseases_catalog, normalize_disease_slug
    from doctor_geo_coords import coords_for_city_country

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
_ALL_DOCTORS_CACHE: list[dict[str, Any]] | None = None
_CONTENT_DOCTORS_CACHE: list[dict[str, Any]] | None = None
_CATALOG_CACHE_LOCK = threading.RLock()


def clear_finder_docs_index() -> None:
    """Drop cached doctor_finder rows (call after a run finishes)."""
    global _FINDER_DOCS_INDEX, _ALL_DOCTORS_CACHE, _CONTENT_DOCTORS_CACHE
    with _CATALOG_CACHE_LOCK:
        _FINDER_DOCS_INDEX = None
        _ALL_DOCTORS_CACHE = None
        _CONTENT_DOCTORS_CACHE = None


def slugify_doctor_name(display_name: str, author_key: str | None = None) -> str:
    """Stable URL slug for a clinician profile."""
    if author_key:
        cleaned = author_key.replace("name:", "").replace("_", "-")
        if cleaned and _SLUG_RE.sub("", cleaned):
            return cleaned[:64].strip("-")
    base = display_name.lower().strip()
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
    explicit_city = str(entry.get("city") or "").strip()
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
    lat, lng = coords_for_city_country(city, country)
    key_papers = entry.get("key_papers") or []
    publications = [
        {
            "pmid": str(p.get("pmid") or ""),
            "title": _decode_stored_text(str(p.get("title") or "")),
            "year": p.get("year"),
            "journal": _decode_stored_text(str(p.get("article_type") or "")),
            "position": "author",
        }
        for p in key_papers
        if isinstance(p, dict) and p.get("pmid")
    ]
    return {
        "slug": slug,
        "name": display_name,
        "specialty": str(entry.get("role") or "Clinical researcher"),
        "role": str(entry.get("role") or ""),
        "institution": str(affiliation or "Affiliation not listed"),
        "city": city,
        "country": country,
        "lat": lat,
        "lng": lng,
        "diseases": diseases,
        "pubmedRole": _role_to_pubmed_role(str(entry.get("role") or "")),
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
        },
        "publications": publications,
        "bio": entry.get("ai_justification") or "",
        "publicSource": "PubMed · Doctor Finder",
        "endorsements": [],
        "contact": "form",
        "source": source,
        "executionId": execution_id,
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
    }


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


def _merge_public_doctor_rows(
    seed: dict[str, Any],
    finder: dict[str, Any],
    *,
    disease_slug: str,
) -> dict[str, Any]:
    """Combine curated seed with a doctor_finder hit (same person)."""
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

    seed_city = str(seed.get("city") or "").strip()
    finder_city = str(finder.get("city") or "").strip()
    city = finder_city if seed_city in {"", "—"} else seed_city
    if not city:
        city = finder_city or seed_city or "—"

    seed_country = str(seed.get("country") or "").strip()
    finder_country = str(finder.get("country") or "").strip()
    country = finder_country or seed_country or "—"

    lat = float(seed.get("lat") or finder.get("lat") or 0.0)
    lng = float(seed.get("lng") or finder.get("lng") or 0.0)

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
    specialty = str(finder.get("specialty") or seed.get("specialty") or "")
    role = str(finder.get("role") or seed.get("role") or "")

    return {
        "slug": slug,
        "name": str(seed.get("name") or finder.get("name") or "Unknown"),
        "specialty": specialty,
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
    }


def _finder_index_matching_seed(seed: dict[str, Any], finder_docs: list[dict[str, Any]], used: set[int]) -> int | None:
    sslug = str(seed.get("slug") or "").strip().lower()
    snk = _canonical_name_key(str(seed.get("name") or ""))
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
    return None


def _merge_seed_and_finder_docs(
    disease_slug: str,
    seeded: list[dict[str, Any]],
    finder_docs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Curated seed + workflow hits: match by slug or normalized name; append unmatched finder rows."""
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
            out.append(row)
            continue
        used_finder.add(j)
        out.append(_merge_public_doctor_rows(seed, finder_docs[j], disease_slug=disease_slug))

    for i, f in enumerate(finder_docs):
        if i in used_finder or not isinstance(f, dict):
            continue
        row = dict(f)
        row["diseases"] = list(dict.fromkeys([*(row.get("diseases") or []), disease_slug]))
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
    """One pass over persisted + in-memory doctor_finder runs (cached per process)."""
    try:
        from .routers import doctor_finder as df_router
    except ImportError:
        from routers import doctor_finder as df_router
    try:
        from .doctor_finder_store import load_successful_reports_for_catalog_index
    except ImportError:
        from doctor_finder_store import load_successful_reports_for_catalog_index

    best_reports: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for slug, (eid, report, started) in load_successful_reports_for_catalog_index().items():
        best_reports[slug] = (started, eid, report)

    with df_router._DOCTOR_FINDER_RUNS_LOCK:
        runs = list(df_router.DOCTOR_FINDER_RUNS.items())

    for execution_id, run in runs:
        if not run.get("done") or run.get("error"):
            continue
        run_slug = str(run.get("catalog_slug") or "").strip().lower()
        if not run_slug:
            run_slug = _disease_slug_for_name(str(run.get("disease_name") or "")) or ""
        if not run_slug:
            continue
        report = run.get("doctor_report")
        if not isinstance(report, dict):
            report = df_router._extract_doctor_report_from_node_outputs(
                run.get("node_outputs") or {},
            )
        if not isinstance(report, dict):
            continue
        started = str(run.get("started_at") or "")
        prev = best_reports.get(run_slug)
        if prev is None or started > prev[0]:
            best_reports[run_slug] = (started, execution_id, report)

    index: dict[str, list[dict[str, Any]] | None] = {}
    for slug, (_started, execution_id, report) in best_reports.items():
        index[slug] = _public_doctors_from_finder_report(
            slug,
            report,
            execution_id=execution_id or None,
        )
    return index


def _finder_docs_index() -> dict[str, list[dict[str, Any]] | None]:
    global _FINDER_DOCS_INDEX
    with _CATALOG_CACHE_LOCK:
        if _FINDER_DOCS_INDEX is None:
            _FINDER_DOCS_INDEX = _build_finder_docs_index()
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

    if live and seeded:
        return "merged", _merge_seed_and_finder_docs(normalized, seeded, live)
    if live:
        return "doctor_finder", live
    if seeded:
        return "content_seed", seeded
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
    global _ALL_DOCTORS_CACHE
    with _CATALOG_CACHE_LOCK:
        if _ALL_DOCTORS_CACHE is not None:
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

        _ALL_DOCTORS_CACHE = list(by_slug.values())
        return _ALL_DOCTORS_CACHE


def get_doctor_by_slug(slug: str) -> dict[str, Any] | None:
    """Single doctor profile from merged catalog."""
    trimmed = slug.strip().lower()
    if not trimmed:
        return None
    return next((doc for doc in list_all_doctors() if doc.get("slug") == trimmed), None)
