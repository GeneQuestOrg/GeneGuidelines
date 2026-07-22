"""FastAPI routes for the guidelines layer (read side).

Four GET endpoints the public site's api-repo calls, mounted under ``/api``:

- ``/diseases/{slug}/source-documents``  -> the source shelf (GL-1)
- ``/diseases/{slug}/guideline-synthesis`` -> the synthesis, 404 when none (GL-2)
- ``/diseases/{slug}/guideline-suggestions`` -> AI suggestions (GL-3a)
- ``/diseases/{slug}/synthesis-signals`` -> per-section signal map (GL-3b)

Lists/maps return empty (200) when a disease has no data; only the single
synthesis 404s — matching how the frontend api-repo degrades (404 -> []/{}/null).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ..account.deps import OptionalUser
from ..account.models import User
from ..shared.locale import resolve_locale
from .contracts import (
    SourceDocResponse,
    SuggestionResponse,
    SuggestionVoteRequest,
    SuggestionVoteResult,
    SynthesisResponse,
    SynthSignalResponse,
)
from .deps import is_verified_doctor, provide_guidelines_service, require_rating_author
from .service import GuidelinesService

router = APIRouter(tags=["guidelines"])

ServiceDep = Annotated[GuidelinesService, Depends(provide_guidelines_service)]
RatingAuthor = Annotated[User, Depends(require_rating_author)]


@router.get(
    "/diseases/{slug}/source-documents",
    response_model=list[SourceDocResponse],
)
def list_source_documents(slug: str, service: ServiceDep) -> list[SourceDocResponse]:
    """The curated source shelf for ``slug`` (empty when none)."""
    return [SourceDocResponse.from_domain(d) for d in service.list_source_documents(slug)]


@router.get(
    "/diseases/{slug}/guideline-synthesis",
    response_model=SynthesisResponse,
)
def get_synthesis(
    slug: str, service: ServiceDep, locale: str = Depends(resolve_locale)
) -> SynthesisResponse:
    """The AI synthesis for ``slug``; 404 when no guideline exists (level c).

    A supported ``?locale=`` overlays the translated document when it is fresh
    (structural/provenance fields always from the English row); otherwise the
    English synthesis is served unchanged.
    """
    synthesis = service.get_synthesis(slug, locale)
    if synthesis is None:
        raise HTTPException(status_code=404, detail="No guideline synthesis")
    return SynthesisResponse.from_domain(synthesis)


@router.get(
    "/diseases/{slug}/guideline-suggestions",
    response_model=list[SuggestionResponse],
)
def list_suggestions(
    slug: str, service: ServiceDep, user: OptionalUser = None
) -> list[SuggestionResponse]:
    """AI suggestions hanging beside the synthesis (empty when none).

    When a clinician is signed in, each suggestion carries that clinician's own
    ``myVote`` so the rail restores the selected verdict.
    """
    my_votes = (
        service.user_suggestion_votes(slug, str(user.id)) if user is not None else {}
    )
    return [
        SuggestionResponse.from_domain(s, my_vote=my_votes.get(s.id))
        for s in service.list_suggestions(slug)
    ]


@router.post(
    "/diseases/{slug}/guideline-suggestions/{suggestion_id}/signal",
    response_model=SuggestionVoteResult,
)
def rate_suggestion(
    slug: str,
    suggestion_id: str,
    body: SuggestionVoteRequest,
    service: ServiceDep,
    user: RatingAuthor,
) -> SuggestionVoteResult:
    """Cast (or clear, with ``verdict: null``) the caller's rating on a suggestion.

    Verified-doctor / researcher / superadmin only (``require_rating_author``).
    Returns the recomputed aggregate signal — "signal, not publication": nothing
    is merged into the official text.
    """
    result = service.cast_suggestion_vote(
        slug,
        suggestion_id,
        user_id=str(user.id),
        is_verified_doctor=is_verified_doctor(user),
        verdict=body.verdict,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No such suggestion")
    return SuggestionVoteResult(signal=result.signal, myVote=result.my_vote)


@router.get(
    "/diseases/{slug}/synthesis-signals",
    response_model=dict[str, SynthSignalResponse],
)
def get_synthesis_signals(slug: str, service: ServiceDep) -> dict[str, SynthSignalResponse]:
    """Per-section asymmetric signal map (empty when none)."""
    return {
        section_id: SynthSignalResponse.from_domain(sig)
        for section_id, sig in service.get_synthesis_signals(slug).items()
    }


__all__ = ["router"]
