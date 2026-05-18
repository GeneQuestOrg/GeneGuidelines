"""Custom disease initial fields for pubmed runs."""
from __future__ import annotations

from backend.guideline_prompt_profile import build_custom_disease_flow_initial_fields


def test_build_custom_disease_flow_initial_fields() -> None:
    fields = build_custom_disease_flow_initial_fields(
        "My rare disease",
        ["MRD", "my disease syndrome"],
    )
    assert fields["disease_slug"] == ""
    assert fields["disease_name"] == "My rare disease"
    assert "MRD" in fields["disease_aliases"]
    assert "custom" in fields["guideline_prompt_block"].lower()
