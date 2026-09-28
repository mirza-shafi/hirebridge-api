"""RELEASE GATE — see docs/00-product-brief.md §8 rule 7.

A ranking model that can see a name, a photo, or a date of birth will use them, and the
resulting bias operates at the scale of every application the platform handles. A failure
here blocks release.
"""

from __future__ import annotations

import pytest

from app.schemas.resume import SourceFact
from app.services.scoring_payload import (
    ALLOWED_SCORING_FIELDS,
    NEVER_SCORED,
    ScoringPayloadError,
    assert_allowlisted,
    build_scoring_payload,
)

# A realistic local CV parse: the protected fields are here because real CVs in Bangladesh
# carry them, not because anyone chose to collect them.
RAW_FACTS = [
    {
        "kind": "experience",
        "payload": {
            "title": "AI Engineer",
            "company": "Autofy Solution",
            "tech": ["Python", "FastAPI", "PostgreSQL"],
            "bullets": [{"id": "b1", "text": "Built a retrieval chatbot"}],
        },
    },
    {
        "kind": "education",
        "payload": {
            "degree": "B.Sc.",
            "field": "Computer Science",
            "institution": "BRAC University",
        },
    },
    {"kind": "certification", "payload": {"name": "DataCamp Associate AI Engineer"}},
    {"kind": "project", "payload": {"description": "Lead capture automation in n8n"}},
    {"kind": "language", "payload": {"name": "Bangla"}},
    {
        # The contaminated one.
        "kind": "experience",
        "payload": {
            "title": "Intern",
            "company": "Mevrik",
            "full_name": "Mirza Md Shafi Uddin",
            "father_name": "Redacted",
            "date_of_birth": "1999-01-01",
            "gender": "male",
            "religion": "redacted",
            "marital_status": "single",
            "nid": "1234567890123",
            "photo_url": "https://example.com/photo.jpg",
            "address": "Dhaka",
            "phone": "01712345678",
            "email": "someone@example.com",
        },
    },
]

FACTS = [
    SourceFact(fact_id="f1", kind="experience", text="Built a retrieval chatbot",
               skills=["Python", "FastAPI"]),
]


@pytest.fixture
def payload() -> dict[str, object]:
    return build_scoring_payload(
        facts=FACTS, raw_facts=RAW_FACTS, years_experience=2.5, location_city="Dhaka"
    )


def test_payload_contains_only_allowlisted_keys(payload: dict[str, object]) -> None:
    assert set(payload) <= ALLOWED_SCORING_FIELDS


@pytest.mark.parametrize("forbidden", sorted(NEVER_SCORED))
def test_no_protected_attribute_survives(payload: dict[str, object], forbidden: str) -> None:
    assert forbidden not in payload


def test_protected_values_do_not_leak_into_any_value(payload: dict[str, object]) -> None:
    """A field name can be dropped while its value rides along inside another field."""
    blob = repr(payload).lower()
    for leaked in (
        "mirza", "shafi", "1999", "male", "single", "1234567890123",
        "photo.jpg", "01712345678", "someone@example.com", "redacted",
    ):
        assert leaked not in blob, f"{leaked!r} leaked into the scoring payload"


def test_legitimate_signal_is_preserved(payload: dict[str, object]) -> None:
    """The gate must not be satisfied by emitting nothing."""
    assert payload["years_experience"] == 2.5
    assert "fastapi" in payload["skills"]  # type: ignore[operator]
    assert "postgres" in payload["skills"]  # type: ignore[operator]
    assert "AI Engineer" in payload["job_titles"]  # type: ignore[operator]
    assert "Autofy Solution" in payload["employers"]  # type: ignore[operator]
    assert "B.Sc." in payload["education_level"]  # type: ignore[operator]
    assert "Computer Science" in payload["field_of_study"]  # type: ignore[operator]
    assert payload["location_city"] == "Dhaka"


def test_allowlist_and_never_scored_do_not_overlap() -> None:
    assert not (ALLOWED_SCORING_FIELDS & NEVER_SCORED)


def test_a_hand_built_payload_with_an_extra_field_is_rejected() -> None:
    with pytest.raises(ScoringPayloadError, match="outside the allowlist"):
        assert_allowlisted({"skills": ["python"], "full_name": "Someone"})


def test_allowlist_is_a_closed_set() -> None:
    """Pins the list. Widening it should require editing this test on purpose."""
    assert ALLOWED_SCORING_FIELDS == {
        "years_experience", "skills", "job_titles", "employers", "education_level",
        "field_of_study", "certifications", "project_descriptions", "languages_spoken",
        "location_city",
    }
