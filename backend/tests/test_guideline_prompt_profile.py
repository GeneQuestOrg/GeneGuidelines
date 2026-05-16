from __future__ import annotations

import unittest

from backend.guideline_prompt_profile import (
    append_disease_prompt_block,
    build_disease_flow_initial_fields,
    format_guideline_prompt_block,
    normalize_guideline_prompt_profile,
)


class GuidelinePromptProfileTests(unittest.TestCase):
    def test_normalize_empty_profile(self) -> None:
        profile = normalize_guideline_prompt_profile(None)
        self.assertEqual(profile["clinicalFraming"], "")
        self.assertEqual(profile["homonymsToAvoid"], [])

    def test_format_block_uses_profile_fields(self) -> None:
        profile = normalize_guideline_prompt_profile(
            {
                "clinicalFraming": "Focus on GNAS bone disease.",
                "pubmedRetrieval": "Use FD and MAS terms.",
                "preferredTerms": ["fibrous dysplasia"],
            }
        )
        disease = {"slug": "fd", "name": "Fibrous Dysplasia", "summary": "GNAS bone disorder.", "gene": "GNAS", "types": []}
        block = format_guideline_prompt_block(profile, disease)
        self.assertIn("Focus on GNAS bone disease.", block)
        self.assertIn("fibrous dysplasia", block)

    def test_build_disease_flow_initial_fields(self) -> None:
        disease = {
            "slug": "fd",
            "name": "Fibrous Dysplasia",
            "summary": "GNAS.",
            "gene": "GNAS",
            "types": [],
            "guidelinePromptProfile": {"clinicalFraming": "FD framing."},
        }
        fields = build_disease_flow_initial_fields(disease)
        self.assertEqual(fields["disease_slug"], "fd")
        self.assertIn("FD framing.", fields["guideline_prompt_block"])

    def test_append_disease_prompt_block_idempotent(self) -> None:
        base = "Do work."
        once = append_disease_prompt_block(base)
        twice = append_disease_prompt_block(once)
        self.assertEqual(once, twice)
        self.assertIn("context.initial.guideline_prompt_block", once)


if __name__ == "__main__":
    unittest.main()
