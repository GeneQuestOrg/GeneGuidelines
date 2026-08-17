"""Every state-changing route is either guarded or listed here as public.

"Public" used to be expressed by the *absence* of a dependency, which is invisible
in review and survives refactors — which is how nine expensive LLM endpoints stayed
open to the internet for months without anyone noticing. This test inverts that: a
mutating route must either carry an auth dependency or appear in
``PUBLIC_MUTATIONS`` below, with a reason. Adding a new open endpoint now means
editing this file, in a diff a reviewer will see.

It walks the live dependency tree of each route rather than grepping decorators, so
router-level guards (``APIRouter(dependencies=[...])``) count — a grep-based version
of this check wrongly accused the flow editor, which is properly superadmin-gated.
"""

from __future__ import annotations

import os

os.environ.setdefault("AGENT_NO_MCP", "1")

from backend.main import app  # noqa: E402 — import after the MCP opt-out

# Dependencies that *refuse* an unauthenticated caller. ``get_optional_user`` is
# deliberately absent: it reads a token when one is present and shrugs otherwise, so
# counting it as a guard would let a wide-open endpoint pass this test — which is
# exactly what happened on the first run, where bootstrap-disease looked protected
# because it takes an OptionalUser to rank the queue.
_AUTH_DEPENDENCIES = frozenset(
    {
        "require_api_key_if_set",
        "require_superadmin",
        "require_role",
        "require_parent_account",
        "require_verified_doctor",
        "require_rating_author",
        "get_current_user",
        "get_claims",
    }
)

_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Open by design. Each entry is a deliberate product decision, not an oversight.
PUBLIC_MUTATIONS: dict[str, str] = {
    "POST /api/pipeline/bootstrap-disease": (
        "The public 'your disease isn't here yet' promise. The production bundle "
        "ships no API key (ADR-001), so gating it would take the feature offline "
        "for everyone. Bounded by the queue's anonymous-session cap, the monthly "
        "token budget and unlisted-until-approve. See test_bootstrap_stays_public."
    ),
    "POST /api/disease-index/wider-search": (
        "The search box itself — a visitor with no account types a symptom or a "
        "misspelling and needs an answer. Costs one LLM call, so it is rate limited."
    ),
    "POST /api/feedback": (
        "Anonymous contact box; a parent must be able to report a wrong claim "
        "without making an account. Rate limited per IP in routers/feedback.py."
    ),
    "POST /api/diseases/{slug}/subscriptions": (
        "Email alerts for a disease. Double opt-in, so a subscription cannot be "
        "forced onto someone else's address."
    ),
}


def _auth_dependencies_of(route: object) -> set[str]:
    """Names of auth dependencies anywhere in this route's dependency tree."""
    found: set[str] = set()
    root = getattr(route, "dependant", None)
    stack = [root] if root is not None else []
    while stack:
        node = stack.pop()
        call = getattr(node, "call", None)
        name = getattr(call, "__name__", None)
        if name:
            found.add(name)
        stack.extend(getattr(node, "dependencies", []) or [])
    return found & _AUTH_DEPENDENCIES


def _mutating_api_routes() -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/api"):
            continue
        for method in sorted((getattr(route, "methods", set()) or set()) & _MUTATING):
            out.append((f"{method} {path}", route))
    return out


def test_every_mutating_route_is_guarded_or_declared_public() -> None:
    unguarded = {
        key
        for key, route in _mutating_api_routes()
        if not _auth_dependencies_of(route) and key not in PUBLIC_MUTATIONS
    }

    assert not unguarded, (
        "these routes change state with no authentication and are not declared "
        f"public: {sorted(unguarded)}. Add a guard, or add an entry to "
        "PUBLIC_MUTATIONS with the reason it must stay open."
    )


def test_public_mutations_list_has_no_dead_entries() -> None:
    """A route that gained a guard (or moved) should leave this list."""
    live = {key for key, _ in _mutating_api_routes()}
    stale = {
        key
        for key, route in _mutating_api_routes()
        if key in PUBLIC_MUTATIONS and _auth_dependencies_of(route)
    }
    missing = set(PUBLIC_MUTATIONS) - live

    assert not stale, f"declared public but now guarded — drop from the list: {sorted(stale)}"
    assert not missing, f"declared public but no such route — stale entry: {sorted(missing)}"
