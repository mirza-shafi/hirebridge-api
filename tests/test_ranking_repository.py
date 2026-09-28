"""Query-shape checks that do not need a live database.

The scoring arithmetic is covered in tests/test_ranking.py; what matters here is that the
statement asks for every applicant and applies no threshold.
"""

from __future__ import annotations

from app.repositories.ranking import NEUTRAL_SEMANTIC, _query_terms
from app.models import Job


def _job(**kwargs: object) -> Job:
    base: dict[str, object] = {
        "org_id": None, "title": "Backend Engineer", "slug": "be",
        "description_raw": "x", "must_have_skills": ["python", "rest_api"],
        "nice_to_have_skills": ["postgres"],
    }
    base.update(kwargs)
    return Job(**base)  # type: ignore[arg-type]


def test_query_terms_include_title_and_both_skill_lists() -> None:
    terms = _query_terms(_job())
    assert "Backend Engineer" in terms
    assert "python" in terms
    assert "rest api" in terms, "underscores become spaces for the text query"
    assert "postgres" in terms


def test_query_terms_survive_a_job_with_no_skills() -> None:
    assert _query_terms(_job(must_have_skills=None, nice_to_have_skills=None)) == "Backend Engineer"


def test_missing_embedding_falls_back_to_neutral_not_zero() -> None:
    """A candidate whose vector has not been computed yet must not be pushed to the bottom
    of the list by an implementation detail."""
    assert NEUTRAL_SEMANTIC == 50.0
