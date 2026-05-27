"""Editorial scope policy — which categories does GeneGuidelines cover?

GeneGuidelines is a registry of *rare genetic* diseases. The platform still
indexes adjacent diseases (rare cancers, rare infectious, …) because users
type those names into the autocomplete and we want to give them a clear
answer ("yes, Tuberculosis exists, here is what it is, but it is out of
scope for our living-guidelines workflow") rather than 0 hits.

This module is the single source of truth for that scope decision so the
UI badge, the route guard inside ``bootstrap-disease`` and the Tier 2
classifier all answer the same question the same way.
"""

from __future__ import annotations

from .models import DiseaseCategory


# Categories that the platform's research workflows are designed for.
# A disease in any *other* category may still be displayed in the
# autocomplete results — it just cannot be promoted to a local record by
# clicking "Run research".
_IN_SCOPE_CATEGORIES: frozenset[DiseaseCategory] = frozenset(
    {"genetic", "predominantly_genetic"}
)

# Categories that should hard-block the "Run research" CTA in the UI even
# when the user clicks through warnings. A clinician overriding a
# multifactorial warning may still be a valuable run; sending the workflow
# at Tuberculosis is just an outright wrong tool.
_HARD_BLOCK_CATEGORIES: frozenset[DiseaseCategory] = frozenset(
    {"infectious", "acquired"}
)


def is_in_scope(category: DiseaseCategory | None) -> bool:
    """Return ``True`` when a disease in this category is fully supported.

    ``None`` (no classification yet) is treated as in scope so unclassified
    Orphanet imports remain searchable until a refresh fills the field in.
    """
    if category is None:
        return True
    return category in _IN_SCOPE_CATEGORIES


def is_hard_blocked(category: DiseaseCategory | None) -> bool:
    """Return ``True`` when a disease in this category cannot be researched.

    The frontend disables the "Run research" button entirely for these;
    backend ``bootstrap-disease`` mirrors the same check before queueing
    the workflows.
    """
    if category is None:
        return False
    return category in _HARD_BLOCK_CATEGORIES


def scope_label(category: DiseaseCategory | None) -> str:
    """Short UI label for the badge next to the suggestion."""
    mapping: dict[DiseaseCategory | None, str] = {
        None: "Unclassified",
        "genetic": "Genetic",
        "predominantly_genetic": "Mostly genetic",
        "multifactorial": "Multifactorial — limited support",
        "infectious": "Infectious — out of scope",
        "acquired": "Acquired — out of scope",
        "unknown": "Unclassified",
    }
    return mapping.get(category, "Unclassified")


__all__ = [
    "is_in_scope",
    "is_hard_blocked",
    "scope_label",
]
