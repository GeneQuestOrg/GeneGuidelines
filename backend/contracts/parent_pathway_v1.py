"""Parent care pathway API contract v1 — numbered next-steps guide for patients and caregivers after diagnosis."""
from __future__ import annotations

PARENT_PATHWAY_CONTRACT_VERSION = "v1"

# Minimum content quality — blocks pytest stubs and empty "chart" saves mistaken for real output.
MIN_ABOUT_SUMMARY_LEN = 180
MIN_TOP_LEVEL_ACTION_STEPS = 3
MIN_ACTION_WHAT_TO_EXPECT_LEN = 70
MIN_ACTION_QUESTION_COUNT = 2

# Validation limits (shared with parent_pathway_schema).
# Parent pathways are short "first steps after diagnosis" guides, not full clinical algorithms.
MAX_TREE_DEPTH = 4
MAX_NODE_COUNT = 18
# Enough room for a rich first-month checklist without becoming a clinician algorithm.
MAX_TOP_LEVEL_CHILDREN = 7
MAX_DECISION_TITLE_LEN = 120
MAX_SUBTITLE_LEN = 280
MAX_ABOUT_TITLE_LEN = 120
# Patient-facing consensus summary (plain language); allow several short paragraphs.
MAX_ABOUT_SUMMARY_LEN = 4500
MAX_ACTION_TITLE_LEN = 200
MAX_HINT_LEN = 200
MAX_SPECIALTY_LEN = 160
MAX_WHAT_TO_EXPECT_LEN = 500
MAX_QUESTION_LEN = 240
MAX_ANSWER_LEN = 80
