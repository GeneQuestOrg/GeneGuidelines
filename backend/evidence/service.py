"""Evidence audit services — thin orchestrators over the repositories.

Two dataclasses with ``slots`` and one job each:

- :class:`EvidenceSnapshotService` — reads + records per-disease snapshots.
- :class:`ArticleAuditService` — reads + records per-article audits.

The service layer owns **input validation** that protects domain
invariants (clamping numeric ranges, capping string lengths, checking
that the referenced disease exists, validating PMIDs and category
tags). Repositories trust their inputs; the API layer ferries Pydantic
DTOs to the service, the service builds repository inputs, the
repository persists. Tests can substitute the InMemory repos and
exercise the validation rules without a database.

Why two services instead of one merged "EvidenceService": the two
concerns drift over time. Snapshot writes happen once per workflow
run; audit writes happen per article inside a run. Snapshot reads are
timeline queries; audit reads are point-in-time per-PMID lookups.
Splitting now keeps each class around 80 LOC and avoids a god-service
that grows whenever either side adds a method.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..content.repository import DiseaseRepo, normalize_slug
from .models import (
    ALL_CATEGORY_TAGS,
    ALL_QUALITY_TIERS,
    ArticleCategoryAudit,
    ArticleCategoryTag,
    DiseaseEvidenceSnapshot,
    EvidenceQualityTier,
)
from .repository import (
    AuditInput,
    AuditRepo,
    SnapshotInput,
    SnapshotRepo,
)


# --- Validation primitives ---------------------------------------------------


class EvidenceWriteError(ValueError):
    """Raised when a write request violates a domain invariant.

    Includes a human-readable message the API layer can surface as a
    ``400`` response detail.
    """


_PMID_RE = re.compile(r"^\d{7,9}$")

# Cap user-provided text fields so a runaway prompt or a malicious
# payload cannot OOM the database. Sizes are loose enough to keep real
# clinical content unaffected.
_MAX_NOTES_LEN = 2000
_MAX_KNOWLEDGE_GAPS_COUNT = 50
_MAX_KNOWLEDGE_GAP_LEN = 200
_MAX_RATIONALE_LEN = 1000
_MAX_MODEL_LEN = 120
_DEFAULT_LIST_LIMIT = 200
_MAX_LIST_LIMIT = 1000


def _clamp_int(value: int, *, low: int, high: int) -> int:
    return max(low, min(int(value), high))


def _clamp_optional_unit(value: float | None) -> float | None:
    """Clamp an optional confidence value to the unit interval."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise EvidenceWriteError(
            f"confidence must be a number, got {value!r}"
        ) from exc
    return max(0.0, min(1.0, v))


def _truncate(text: str | None, *, limit: int) -> str:
    if text is None:
        return ""
    raw = str(text)
    if len(raw) <= limit:
        return raw
    return raw[:limit]


def _clean_knowledge_gaps(items: object) -> tuple[str, ...]:
    """Strip, dedupe, cap length + count."""
    if items is None:
        return ()
    if not isinstance(items, (list, tuple)):
        raise EvidenceWriteError(
            "knowledge_gaps must be a list of strings"
        )
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in items:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text:
            continue
        text = text[:_MAX_KNOWLEDGE_GAP_LEN]
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= _MAX_KNOWLEDGE_GAPS_COUNT:
            break
    return tuple(cleaned)


def _filter_category_tags(
    items: object, *, field_label: str, require_non_empty: bool
) -> tuple[ArticleCategoryTag, ...]:
    """Return a tuple of valid tags. Unknown tags raise."""
    if items is None:
        if require_non_empty:
            raise EvidenceWriteError(f"{field_label} must contain at least one tag")
        return ()
    if not isinstance(items, (list, tuple)):
        raise EvidenceWriteError(f"{field_label} must be a list of tags")
    known = set(ALL_CATEGORY_TAGS)
    result: list[ArticleCategoryTag] = []
    seen: set[str] = set()
    for raw in items:
        if not isinstance(raw, str):
            raise EvidenceWriteError(
                f"{field_label} entries must be strings"
            )
        if raw not in known:
            raise EvidenceWriteError(
                f"{field_label} contains unknown tag {raw!r} — "
                f"valid tags: {sorted(known)}"
            )
        if raw in seen:
            continue
        seen.add(raw)
        result.append(raw)  # type: ignore[arg-type]
    if require_non_empty and not result:
        raise EvidenceWriteError(
            f"{field_label} must contain at least one tag"
        )
    return tuple(result)


def _validate_quality_tier(
    value: object,
) -> EvidenceQualityTier | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise EvidenceWriteError(
            f"quality_tier must be a string, got {type(value).__name__}"
        )
    if value not in ALL_QUALITY_TIERS:
        raise EvidenceWriteError(
            f"quality_tier {value!r} is not one of {list(ALL_QUALITY_TIERS)}"
        )
    return value  # type: ignore[return-value]


def _validate_pmid(pmid: str) -> str:
    raw = str(pmid).strip()
    if not _PMID_RE.match(raw):
        raise EvidenceWriteError(
            f"pmid {pmid!r} is not a valid PubMed identifier (7-9 digits)"
        )
    return raw


def _resolve_disease_slug(
    slug: str, *, disease_repo: DiseaseRepo
) -> str:
    normalized = normalize_slug(slug)
    if normalized is None:
        raise EvidenceWriteError(
            f"disease_slug {slug!r} is not a valid slug"
        )
    if disease_repo.get(normalized) is None:
        raise EvidenceWriteError(
            f"disease_slug {normalized!r} does not exist"
        )
    return normalized


# --- Services ----------------------------------------------------------------


@dataclass(slots=True)
class EvidenceSnapshotService:
    """Read + write snapshots for the public timeline + admin dashboard."""

    snapshot_repo: SnapshotRepo
    disease_repo: DiseaseRepo

    def list_for_disease(
        self, slug: str, *, limit: int = 20
    ) -> list[DiseaseEvidenceSnapshot] | None:
        """Return the timeline of snapshots, newest first.

        Returns ``None`` when the disease itself is unknown so the
        API layer can produce a clean 404 distinct from "disease exists
        but no snapshots yet" (which is an empty list).
        """
        normalized = normalize_slug(slug)
        if normalized is None or self.disease_repo.get(normalized) is None:
            return None
        capped = _clamp_int(limit, low=1, high=_DEFAULT_LIST_LIMIT)
        return self.snapshot_repo.list_for_disease(normalized, limit=capped)

    def get_latest(self, slug: str) -> DiseaseEvidenceSnapshot | None:
        """Most-recent snapshot for the disease, or ``None`` if none / unknown."""
        normalized = normalize_slug(slug)
        if normalized is None or self.disease_repo.get(normalized) is None:
            return None
        return self.snapshot_repo.get_latest(normalized)

    def get(self, snapshot_id: int) -> DiseaseEvidenceSnapshot | None:
        if snapshot_id is None or snapshot_id <= 0:
            return None
        return self.snapshot_repo.get(int(snapshot_id))

    def record(
        self,
        *,
        disease_slug: str,
        triggered_by_execution_id: str | None = None,
        triggered_by_flow_key: str | None = None,
        articles_seen_total: int = 0,
        articles_cited_in_guideline: int = 0,
        pmids_verified_ok: int = 0,
        pmids_scrubbed: int = 0,
        category_counts: object = None,
        quality_counts: object = None,
        knowledge_gaps: object = None,
        paragraphs_total: int = 0,
        paragraphs_passed_eval: int = 0,
        avg_synthesis_confidence: float | None = None,
        evidence_score: int = 0,
        confidence_index: int = 0,
        notes: str = "",
    ) -> DiseaseEvidenceSnapshot:
        """Persist a new snapshot.

        Caller is the workflow capture hook (or a future admin override
        endpoint). Validation here is defensive — accept noisy inputs
        from upstream callers and normalize before persistence.
        """
        from .models import EvidenceCategoryCounts, EvidenceQualityCounts

        slug = _resolve_disease_slug(disease_slug, disease_repo=self.disease_repo)
        category_value = _coerce_category_counts(category_counts)
        quality_value = _coerce_quality_counts(quality_counts)
        snapshot_input = SnapshotInput(
            disease_slug=slug,
            triggered_by_execution_id=_optional_str(triggered_by_execution_id),
            triggered_by_flow_key=_optional_str(triggered_by_flow_key),
            articles_seen_total=max(0, int(articles_seen_total)),
            articles_cited_in_guideline=max(0, int(articles_cited_in_guideline)),
            pmids_verified_ok=max(0, int(pmids_verified_ok)),
            pmids_scrubbed=max(0, int(pmids_scrubbed)),
            category_counts=category_value or EvidenceCategoryCounts(),
            quality_counts=quality_value or EvidenceQualityCounts(),
            knowledge_gaps=_clean_knowledge_gaps(knowledge_gaps),
            paragraphs_total=max(0, int(paragraphs_total)),
            paragraphs_passed_eval=max(0, int(paragraphs_passed_eval)),
            avg_synthesis_confidence=_clamp_optional_unit(avg_synthesis_confidence),
            evidence_score=_clamp_int(evidence_score, low=0, high=100),
            confidence_index=_clamp_int(confidence_index, low=0, high=100),
            notes=_truncate(notes, limit=_MAX_NOTES_LEN),
        )
        return self.snapshot_repo.insert(snapshot_input)


@dataclass(slots=True)
class ArticleAuditService:
    """Read + write per-article AI categorisation audit rows."""

    audit_repo: AuditRepo
    disease_repo: DiseaseRepo

    def list_for_disease(
        self, slug: str, *, limit: int = _DEFAULT_LIST_LIMIT
    ) -> list[ArticleCategoryAudit] | None:
        normalized = normalize_slug(slug)
        if normalized is None or self.disease_repo.get(normalized) is None:
            return None
        capped = _clamp_int(limit, low=1, high=_MAX_LIST_LIMIT)
        return self.audit_repo.list_for_disease(normalized, limit=capped)

    def list_for_pmid(self, pmid: str) -> list[ArticleCategoryAudit]:
        try:
            normalized = _validate_pmid(pmid)
        except EvidenceWriteError:
            return []
        return self.audit_repo.list_for_pmid(normalized)

    def get(self, audit_id: int) -> ArticleCategoryAudit | None:
        if audit_id is None or audit_id <= 0:
            return None
        return self.audit_repo.get(int(audit_id))

    def record(
        self,
        *,
        pmid: str,
        disease_slug: str,
        triggered_by_execution_id: str | None = None,
        ai_categories: object = None,
        ai_rationale: str = "",
        ai_model: str = "",
        ai_confidence: float | None = None,
        quality_tier: object = None,
    ) -> ArticleCategoryAudit:
        """Persist a new (or refreshed) article audit."""
        slug = _resolve_disease_slug(disease_slug, disease_repo=self.disease_repo)
        pmid_value = _validate_pmid(pmid)
        categories = _filter_category_tags(
            ai_categories,
            field_label="ai_categories",
            require_non_empty=True,
        )
        tier = _validate_quality_tier(quality_tier)
        audit_input = AuditInput(
            pmid=pmid_value,
            disease_slug=slug,
            triggered_by_execution_id=_optional_str(triggered_by_execution_id),
            ai_categories=categories,
            ai_rationale=_truncate(ai_rationale, limit=_MAX_RATIONALE_LEN),
            ai_model=_truncate(ai_model, limit=_MAX_MODEL_LEN),
            ai_confidence=_clamp_optional_unit(ai_confidence),
            quality_tier=tier,
        )
        return self.audit_repo.upsert(audit_input)


# --- Helpers shared between services -----------------------------------------


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return str(value)


def _coerce_category_counts(value: object):
    """Accept either a domain ``EvidenceCategoryCounts`` or a dict-like payload."""
    from .models import EvidenceCategoryCounts

    if value is None:
        return None
    if isinstance(value, EvidenceCategoryCounts):
        return value
    if isinstance(value, dict):
        return EvidenceCategoryCounts(
            treatment=_safe_int(value.get("treatment")),
            monitoring=_safe_int(value.get("monitoring")),
            diagnosis=_safe_int(value.get("diagnosis")),
            pathophysiology=_safe_int(value.get("pathophysiology")),
            case_report=_safe_int(value.get("case_report")),
            review=_safe_int(value.get("review")),
            epidemiology=_safe_int(value.get("epidemiology")),
            other=_safe_int(value.get("other")),
        )
    raise EvidenceWriteError(
        "category_counts must be a dict or EvidenceCategoryCounts"
    )


def _coerce_quality_counts(value: object):
    from .models import EvidenceQualityCounts

    if value is None:
        return None
    if isinstance(value, EvidenceQualityCounts):
        return value
    if isinstance(value, dict):
        return EvidenceQualityCounts(
            high=_safe_int(value.get("high")),
            moderate=_safe_int(value.get("moderate")),
            low=_safe_int(value.get("low")),
            very_low=_safe_int(value.get("very_low")),
        )
    raise EvidenceWriteError(
        "quality_counts must be a dict or EvidenceQualityCounts"
    )


def _safe_int(value: object) -> int:
    if value is None:
        return 0
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


__all__ = [
    "EvidenceSnapshotService",
    "ArticleAuditService",
    "EvidenceWriteError",
]
