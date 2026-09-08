"""Which presentation a doctor handles, not merely whether they have seen the disease.

FD splits into presentations managed by entirely different people: the craniofacial
surgeon, the orthopaedic surgeon with a femur, the endocrinologist with McCune-
Albright. A parent whose child has a skull lesion is asking a narrower question than
"has this doctor touched FD", and a directory that answers the broad one leaves them
to guess.

Derived only from stored fields, so a re-run reproduces the same tags exactly, and
every tag carries the text it came from — nothing here is a model's opinion.
"""

from __future__ import annotations

from backend.doctor_scope import ScopeTag, derive_scope, scope_keys


def test_the_case_this_exists_for() -> None:
    """The surgeon a family with a craniofacial child needs to find. No publications
    at all — the scope comes from his specialty and a children's hospital."""
    tags = derive_scope(
        {
            "specialty": "Oral and maxillofacial surgery",
            "institution": "WSSD Olsztyn · Dowgierd Clinic",
        }
    )

    assert [t.key for t in tags] == ["craniofacial", "paediatric"]
    assert tags[0].basis == "Oral and maxillofacial surgery"


def test_anatomy_in_a_title_places_the_case() -> None:
    """Real title from the FD directory: the ethmoid is a skull bone, and a
    10-year-old is a child. Both are read from the same sentence."""
    tags = derive_scope(
        {"publications": [{"title": "Fibrous Dysplasia of the Ethmoid Bone Diagnosed in a 10-Year-Old Patient."}]}
    )

    assert scope_keys({"publications": [{"title": "Fibrous Dysplasia of the Ethmoid Bone Diagnosed in a 10-Year-Old Patient."}]}) == [
        "craniofacial",
        "paediatric",
    ]
    assert "ethmoid" in tags[0].basis


def test_an_adult_age_is_not_paediatric() -> None:
    """"40-year-old" must not become a paediatric tag — the whole point is telling a
    parent whether this person treats children."""
    assert scope_keys({"publications": [{"title": "Fibrous dysplasia of the skull in a 40-year-old patient"}]}) == [
        "craniofacial"
    ]


def test_the_endocrine_axis_is_kept_separate_from_surgery() -> None:
    keys = scope_keys(
        {
            "specialty": "Endocrinology",
            "publications": [{"title": "Precocious puberty in McCune-Albright syndrome"}],
        }
    )

    assert keys == ["endocrine"]


def test_a_femur_is_not_a_skull() -> None:
    assert scope_keys({"publications": [{"title": "Shepherd's crook deformity of the femur in fibrous dysplasia"}]}) == [
        "skeletal"
    ]


def test_a_doctor_we_know_nothing_specific_about_gets_no_tags() -> None:
    """Silence rather than a guess: a wrong scope sends a family to the wrong clinic,
    a missing one costs them one extra question."""
    assert derive_scope({"name": "Dr X", "institution": "Department of Otolaryngology"}) == []


def test_a_department_name_alone_never_implies_anatomy() -> None:
    """Otolaryngology sees skull-base FD, but the department name is not evidence that
    this doctor did — the publication title is."""
    assert "craniofacial" not in scope_keys({"institution": "Department of Otolaryngology - Head and Neck Surgery"})


def test_the_strongest_basis_wins_and_tags_do_not_duplicate() -> None:
    doctor = {
        "specialty": "Oral and maxillofacial surgery",
        "publications": [
            {"title": "Fibrous dysplasia of the orbit"},
            {"title": "Maxillary fibrous dysplasia in children"},
        ],
    }

    tags = derive_scope(doctor)

    assert [t.key for t in tags] == ["craniofacial", "paediatric"]
    # Publication evidence outranks the specialty string for the same tag.
    assert "orbit" in tags[0].basis


def test_every_tag_carries_the_text_it_came_from() -> None:
    """A claim a reader cannot check is the thing this whole codebase keeps removing."""
    for tag in derive_scope(
        {"specialty": "Endocrinology", "publications": [{"title": "Fibrous dysplasia of the skull in a child"}]}
    ):
        assert isinstance(tag, ScopeTag)
        assert tag.basis.strip(), f"{tag.key} has no basis"


def test_derivation_is_deterministic() -> None:
    """Reproducible results were the requirement: same input, same tags, same order."""
    doctor = {
        "specialty": "Oral and maxillofacial surgery",
        "institution": "Children's Hospital",
        "publications": [{"title": "Fibrous dysplasia of the orbit in a 9-year-old"}],
    }

    assert derive_scope(doctor) == derive_scope(doctor)
