"""Shared long strings for patient pathway schema tests (min length guards)."""
from __future__ import annotations

# Must be >= MIN_ABOUT_SUMMARY_LEN (180) in backend.contracts.parent_pathway_v1
ABOUT_SUMMARY_MIN: str = (
    "This block exists so automated tests satisfy the same minimum length as production saves. "
    "In real charts it is the patient-facing summary of consensus: what the diagnosis means in "
    "everyday words, what usually happens next, and what families should watch for. "
    "Padding would be wrong in production — here we only need enough characters for the validator."
)


def three_action_steps(*, bad_pmid_step: int | None = None) -> list[dict]:
    """Three distinct top-level checklist steps for publish / schema tests."""
    steps: list[dict] = [
        {
            "id": "step-records",
            "action": True,
            "title": "Collect letters, imaging, and lab results in one folder",
            "specialty": "Your GP or family doctor",
            "whatToExpect": (
                "Ask clinics for copies of the diagnosis letter and any scans or blood tests you already had. "
                "You do not need everything on day one — start with what you have and add as you find more."
            ),
            "questions": [
                "Can someone help us request records if English is hard for us?",
                "Should we bring paper copies or are phone photos enough for the first visit?",
            ],
            "citations": ["31337488"],
            "evidenceGap": False,
        },
        {
            "id": "step-genetics",
            "action": True,
            "title": "Schedule genetics or DNA confirmation if your team recommends it",
            "specialty": "Clinical genetics team",
            "whatToExpect": (
                "A genetic counsellor or doctor explains why a test is offered, how it is done, and how long "
                "results take. You can say no or ask for more time — bring another adult if you want support."
            ),
            "questions": [
                "What exactly does this test show for our family?",
                "How and when will we get results, and who explains them?",
            ],
            "citations": ["31337488"],
            "evidenceGap": False,
        },
        {
            "id": "step-followup",
            "action": True,
            "title": "Book the follow-up visit your specialist asked for",
            "specialty": "Specialist clinic named on your discharge or referral letter",
            "whatToExpect": (
                "This visit is usually about the plan ahead — monitoring, pain, growth, or other checks your "
                "team already mentioned. Write down new symptoms since the last appointment."
            ),
            "questions": [
                "What should we track day to day until we see you again?",
                "Who do we phone if symptoms get worse before that date?",
            ],
            "citations": ["31337488"],
            "evidenceGap": False,
        },
    ]
    if bad_pmid_step is not None and 1 <= bad_pmid_step <= len(steps):
        steps[bad_pmid_step - 1] = {**steps[bad_pmid_step - 1], "citations": ["99999999"]}
    return steps
