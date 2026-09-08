"""Two questions, asked because nobody else is asking them — now in real columns.

The directory can be assembled from PubMed and registries; the route to the right
clinician cannot. It exists only in families' heads: the founder found the surgeon who
made the correct call privately, and only then was referred into the institution. No
registry records who sends whom.

So the form asks what the clinician got right, and how the family reached them. It
does NOT ask who got it wrong — publishing that beside a name is a legal risk and the
fastest way to lose the clinicians the foundation needs on side, however entitled a
family is to the anger.

These first shipped inside the free-text column behind markers, because migrations
were applied by hand and bundling one into a deploy felt riskier than it should have.
Migration d3a71f5c2e88 gives them real columns and lifts the marker-era answers out of
the prose; start-up now runs alembic itself, so that trade-off is gone for good.
"""

from __future__ import annotations

import importlib.util
import pathlib


def _migration():
    path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "d3a71f5c2e88_contribution_answers.py"
    )
    spec = importlib.util.spec_from_file_location("_mig", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_request_contract_carries_both_questions() -> None:
    from backend.doctor_contributions.contracts import (
        SubmitDoctorRequest,
        SubmitParentRecRequest,
    )

    for model in (SubmitDoctorRequest, SubmitParentRecRequest):
        assert "what_helped" in model.model_fields
        assert "how_found" in model.model_fields


def test_both_domain_models_carry_them_too() -> None:
    """A field that stops at the API boundary is a field that never reaches anyone."""
    from backend.doctor_contributions.models import DoctorSubmission, ParentRec

    for model in (DoctorSubmission, ParentRec):
        assert "what_helped" in model.__dataclass_fields__
        assert "how_found" in model.__dataclass_fields__


def test_nothing_asks_who_got_it_wrong() -> None:
    """A deliberate absence, recorded so it is not "helpfully" added later."""
    from backend.doctor_contributions.contracts import SubmitDoctorRequest

    fields = " ".join(SubmitDoctorRequest.model_fields)
    for banned in ("wrong", "misdiagnos", "complaint", "blame", "negative"):
        assert banned not in fields


def test_the_migration_recovers_marker_era_answers() -> None:
    """Anything submitted between the two deploys lives as prose behind markers and
    must not be stranded there."""
    split = _migration()._split

    body = "ogólna uwaga\n\n[what-helped]\nwłaściwe rozpoznanie\n\n[how-found]\nrodzic z grupy"

    assert split(body) == ("właściwe rozpoznanie", "rodzic z grupy")


def test_a_note_from_before_the_questions_existed_yields_nothing() -> None:
    """It was one answer to one question; inventing two would be worse than none."""
    assert _migration()._split("po prostu dobry lekarz") == ("", "")


def test_multiline_answers_survive_the_backfill() -> None:
    split = _migration()._split
    story = "Trafiliśmy przez znajomych.\nWcześniej byliśmy w dwóch ośrodkach."

    assert split(f"[how-found]\n{story}")[1] == story


def test_the_backfill_uses_python_not_a_postgres_regex() -> None:
    """The SQL version used lookahead, which Postgres POSIX regex does not support. It
    passed against empty tables and would have failed the first deploy with data in
    them — the tables were empty, so nothing evaluated the pattern."""
    source = (
        pathlib.Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "d3a71f5c2e88_contribution_answers.py"
    ).read_text()

    assert "SUBSTRING(" not in source
    assert "(?=" not in source
