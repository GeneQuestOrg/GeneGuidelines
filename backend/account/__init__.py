"""Account domain — authenticated users, roles, and Auth0 JWT verification.

This vertical mirrors ``backend/content/``: a thin ``api`` controller delegates
to a stateless ``service``, which talks to a ``repository`` (SQLAlchemy 2.0
Core, not ORM) over the shared persistence layer. Domain objects are frozen
dataclasses (``models``); the HTTP boundary uses Pydantic DTOs (``contracts``).

Auth0 is the identity provider *only* — it issues and signs the JWT. Every
authorisation fact the app reasons about (role, verification, ORCID,
institution) lives in our ``users`` table, never in IdP metadata. See
``docs/adr/003-auth0-eu-idp-and-account-model.md`` for the rationale.

Public API for cross-module imports (AUTH-2/AUTH-3 build on these):

- :class:`backend.account.models.User` — frozen domain object
- :class:`backend.account.models.Role` — role enum
- :class:`backend.account.deps` — ``CurrentUser`` / ``OptionalUser`` /
  ``require_role`` / ``require_superadmin`` / ``require_verified_doctor``
- :data:`backend.account.api.router` — FastAPI router (mounted by ``backend.main``)
"""
