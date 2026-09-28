"""Resume parser boundary behaviour."""

from __future__ import annotations

from datetime import date

from app.agents.resume_parser.mapping import completeness_score, needs_review, to_fact_rows
from app.schemas.profile import (
    ParsedBullet,
    ParsedContact,
    ParsedEducation,
    ParsedExperience,
    ParsedFact,
    ParsedProfile,
    ParsedSimpleItem,
)


def _profile(*facts: ParsedFact, **kwargs: object) -> ParsedProfile:
    return ParsedProfile(contact=ParsedContact(full_name="Test"), facts=list(facts), **kwargs)  # type: ignore[arg-type]


EXPERIENCE = ParsedFact(
    kind="experience",
    confidence=0.95,
    experience=ParsedExperience(
        company="Autofy Solution",
        title="AI Engineer",
        date_range_raw="Jan'24 - Present",
        bullets=[ParsedBullet(id="b1", text="Built a retrieval chatbot")],
        tech=["Python", "FastAPI", "PostgreSQL"],
    ),
)


def test_raw_dates_are_normalised_deterministically() -> None:
    row = to_fact_rows(_profile(EXPERIENCE))[0]
    assert row["start_date"] == date(2024, 1, 1)
    assert row["end_date"] is None, "a current role has no end date"
    assert row["payload"]["raw_date"] == "Jan'24 - Present", "the original is kept for display"


def test_ambiguous_dates_are_left_empty_rather_than_guessed() -> None:
    fact = ParsedFact(
        kind="experience", confidence=0.6,
        experience=ParsedExperience(company="X", date_range_raw="03/04 - 05/06"),
    )
    row = to_fact_rows(_profile(fact))[0]
    assert row["start_date"] is None and row["end_date"] is None


def test_tech_is_canonicalised() -> None:
    row = to_fact_rows(_profile(EXPERIENCE))[0]
    assert row["payload"]["tech"] == ["fastapi", "postgres", "python"]


def test_bullets_keep_their_ids_for_citation() -> None:
    row = to_fact_rows(_profile(EXPERIENCE))[0]
    assert row["payload"]["bullets"] == [{"id": "b1", "text": "Built a retrieval chatbot"}]


def test_position_preserves_cv_order() -> None:
    education = ParsedFact(
        kind="education", confidence=0.9,
        education=ParsedEducation(institution="BRAC University", degree="B.Sc."),
    )
    rows = to_fact_rows(_profile(EXPERIENCE, education))
    assert [r["position"] for r in rows] == [0, 1]


def test_low_confidence_facts_are_flagged_for_user_review() -> None:
    uncertain = ParsedFact(
        kind="experience", confidence=0.55,
        experience=ParsedExperience(company="Ambiguous Co"),
    )
    rows = to_fact_rows(_profile(EXPERIENCE, uncertain))
    flagged = needs_review(rows)
    assert len(flagged) == 1
    assert flagged[0]["payload"]["company"] == "Ambiguous Co"


def test_nothing_is_verified_until_the_user_says_so() -> None:
    assert all(not row["verified_by_user"] for row in to_fact_rows(_profile(EXPERIENCE)))


def test_malformed_fact_is_dropped_not_half_written() -> None:
    """A fact whose payload is missing produces no row rather than an empty one."""
    broken = ParsedFact(kind="experience", confidence=0.9)  # no experience payload
    assert to_fact_rows(_profile(broken)) == []


def test_simple_items_map_through() -> None:
    cert = ParsedFact(
        kind="certification", confidence=1.0,
        item=ParsedSimpleItem(name="DataCamp Associate AI Engineer", date_raw="2025"),
    )
    row = to_fact_rows(_profile(cert))[0]
    assert row["payload"]["name"] == "DataCamp Associate AI Engineer"
    assert row["start_date"] == date(2025, 1, 1)


def test_completeness_rewards_a_fuller_profile() -> None:
    thin = to_fact_rows(_profile(EXPERIENCE))
    education = ParsedFact(
        kind="education", confidence=0.9,
        education=ParsedEducation(institution="BRAC University", degree="B.Sc."),
    )
    fuller = to_fact_rows(_profile(EXPERIENCE, education))
    assert completeness_score(fuller) > completeness_score(thin)
    assert 0 <= completeness_score(fuller) <= 100


def test_extraction_warnings_survive() -> None:
    profile = _profile(extraction_warnings=["Page 2 contained no extractable text."])
    assert profile.extraction_warnings
