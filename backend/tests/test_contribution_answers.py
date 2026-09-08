"""Two questions, asked because nobody else is asking them.

The directory can be built from PubMed and registries; the route to the right
clinician cannot. It exists only in families' heads — the founder found the surgeon
who made the correct call privately, and only then was referred into the institution.
No registry records who sends whom.

So the submission form asks what the clinician got right, and how the family reached
them. It does NOT ask who got it wrong: publishing that beside a name is a legal risk
and the fastest way to lose the clinicians the foundation needs on side, however
justified the anger.

Migrations here are applied by hand, and shipping code that reads a column before
someone runs the migration is how this product 500'd earlier today. With effectively
no submissions yet, the answers ride in the existing note column behind stable
markers, so a later migration can recover every one of them.
"""

from __future__ import annotations

from backend.doctor_contributions.answers import compose_note, parse_note


def test_both_answers_survive_a_round_trip() -> None:
    note = compose_note(
        what_helped="postawił właściwe rozpoznanie",
        how_found="podpowiedź od rodzica z grupy",
    )

    assert parse_note(note) == {
        "note": "",
        "what_helped": "postawił właściwe rozpoznanie",
        "how_found": "podpowiedź od rodzica z grupy",
    }


def test_a_note_written_before_the_questions_existed_stays_whole() -> None:
    """It was one answer to one question; splitting it would invent structure that was
    never there."""
    assert parse_note("po prostu dobry lekarz") == {
        "note": "po prostu dobry lekarz",
        "what_helped": "",
        "how_found": "",
    }


def test_free_text_and_structured_answers_coexist() -> None:
    note = compose_note(note="ogólna uwaga", what_helped="A", how_found="B")

    parsed = parse_note(note)

    assert parsed["note"] == "ogólna uwaga"
    assert parsed["what_helped"] == "A"
    assert parsed["how_found"] == "B"


def test_an_empty_answer_leaves_no_marker_behind() -> None:
    """An empty section would parse back as an answered-but-blank question, which is a
    different claim from not having been asked."""
    note = compose_note(what_helped="A")

    assert "how-found" not in note
    assert parse_note(note)["how_found"] == ""


def test_multiline_answers_are_not_truncated_at_the_first_newline() -> None:
    story = "Trafiliśmy przez znajomych.\nWcześniej byliśmy w dwóch ośrodkach."
    parsed = parse_note(compose_note(how_found=story))

    assert parsed["how_found"] == story


def test_the_request_contract_carries_both_questions() -> None:
    from backend.doctor_contributions.contracts import (
        SubmitDoctorRequest,
        SubmitParentRecRequest,
    )

    for model in (SubmitDoctorRequest, SubmitParentRecRequest):
        assert "what_helped" in model.model_fields
        assert "how_found" in model.model_fields


def test_nothing_asks_who_got_it_wrong() -> None:
    """A deliberate absence, recorded so it is not "helpfully" added later."""
    from backend.doctor_contributions.contracts import SubmitDoctorRequest

    fields = " ".join(SubmitDoctorRequest.model_fields)
    for banned in ("wrong", "misdiagnos", "complaint", "blame", "negative"):
        assert banned not in fields
