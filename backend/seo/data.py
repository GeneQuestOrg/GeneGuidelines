"""What the server-rendered pages read, and from where: the same services the public API serves.

One small seam, so the pages never reach past it into SQL and tests can hand in fakes. Every call goes through the services' own rules — `DiseaseService.list` returns listed diseases only, `GuidelinesService.get_synthesis` withholds an ungrounded synthesis, the doctor catalogue serves clinical-axis rows — so a server-rendered page cannot show something the API would not.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..content.models import Disease
from ..content.trials_models import Trial
from ..guidelines.models import GuidelineSynthesis, SourceDocument


@dataclass(frozen=True)
class SeoData:
    """The reads a server-rendered page may make. Each returns ``None``/empty for "not there"; an exception means "could not ask", and the caller serves the plain shell."""

    list_diseases: Callable[[str], list[Disease]]
    get_disease: Callable[[str, str], Disease | None]
    get_synthesis: Callable[[str, str], GuidelineSynthesis | None]
    list_source_documents: Callable[[str], list[SourceDocument]]
    list_doctors_for_disease: Callable[[str], list[dict[str, Any]]]
    get_doctor: Callable[[str], dict[str, Any] | None]
    list_trials_for_disease: Callable[[str], list[Trial] | None]
    # The published guideline-points block (dict) or None; defaulted so a fake can leave it out.
    get_guideline_points: Callable[[str], dict | None] = lambda slug: None


def production_data() -> SeoData:
    """Wire the production services, the way the API's ``Depends`` providers do."""
    from ..content.deps import (
        provide_disease_repo,
        provide_disease_service,
        provide_doctor_count,
        provide_translation_repo,
        provide_trial_count,
        provide_trial_repo,
        provide_trial_service,
    )
    from ..doctor_catalog import get_doctor_by_slug, get_doctors_for_disease
    from ..guidelines.deps import (
        provide_guidelines_repo,
        provide_guidelines_service,
        provide_synthesis_translation_repo,
    )

    disease_repo = provide_disease_repo()
    diseases = provide_disease_service(
        repo=disease_repo,
        doctor_count=provide_doctor_count(),
        trial_count=provide_trial_count(),
        translation_repo=provide_translation_repo(),
    )
    guidelines = provide_guidelines_service(
        repo=provide_guidelines_repo(),
        synthesis_translation_repo=provide_synthesis_translation_repo(),
    )
    trials = provide_trial_service(trial_repo=provide_trial_repo(), disease_repo=disease_repo)

    def doctors_for(slug: str) -> list[dict[str, Any]]:
        return list(get_doctors_for_disease(slug).get("doctors") or [])

    return SeoData(
        list_diseases=lambda locale: diseases.list(locale=locale),
        get_disease=lambda slug, locale: diseases.get(slug, locale),
        get_synthesis=lambda slug, locale: guidelines.get_synthesis(slug, locale),
        list_source_documents=guidelines.list_source_documents,
        list_doctors_for_disease=doctors_for,
        get_doctor=get_doctor_by_slug,
        list_trials_for_disease=trials.list_for_disease,
        get_guideline_points=_published_points,
    )


def _published_points(slug: str) -> dict | None:
    from ..guidelines.points.store import published_block

    try:
        return published_block(slug)
    except Exception:  # noqa: BLE001 - an unmigrated table means no block on the page, not a failed page
        return None
