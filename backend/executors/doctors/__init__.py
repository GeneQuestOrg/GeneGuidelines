"""Executors for the doctors domain.

Grouped so the boundary is visible in the tree, not only in filenames. Nothing here
may import from a sibling domain package; `backend/tests/test_domain_boundaries.py`
enforces that, because the failure it prevents — polishing one flow and quietly
breaking another — is invisible until a user hits it.
"""
