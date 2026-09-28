"""JD parser boundary behaviour.

Model quality is measured by the eval suite; these tests pin the deterministic mapping
around it — the part that must not drift when a prompt changes.
"""

from __future__ import annotations

from app.agents.jd_parser.mapping import slugify, to_job_fields
from app.schemas.job import RedFlag, Requirement, StructuredJD


def _jd(**overrides: object) -> StructuredJD:
    base: dict[str, object] = {
        "title": "Senior Backend Engineer",
        "seniority": "senior",
        "requirements": [
            Requirement(text="3+ years with Python", type="must", skill="Python", years=3),
            Requirement(text="Experience with PostgreSQL", type="must", skill="PostgreSQL"),
            Requirement(text="Familiarity with Next.js", type="nice", skill="Next.js"),
            Requirement(text="Exposure to K8s a plus", type="nice", skill="K8s"),
        ],
    }
    base.update(overrides)
    return StructuredJD(**base)  # type: ignore[arg-type]


def test_skills_are_canonicalised_at_the_boundary() -> None:
    fields = to_job_fields(_jd())
    assert fields["must_have_skills"] == ["postgres", "python"]
    assert fields["nice_to_have_skills"] == ["kubernetes", "nextjs"]


def test_canonicalisation_makes_cv_and_jd_spellings_match() -> None:
    """A CV saying "Postgres" must match a JD saying "PostgreSQL"."""
    fields = to_job_fields(_jd())
    assert "postgres" in fields["must_have_skills"]
    assert "postgresql" not in fields["must_have_skills"]


def test_red_flags_survive_to_the_job_record() -> None:
    jd = _jd(
        red_flags=[
            RedFlag(
                text="Male candidates preferred",
                category="gender",
                explanation="Restricts applicants by gender.",
                suggestion="Remove the restriction.",
            )
        ]
    )
    fields = to_job_fields(jd)
    assert len(fields["red_flags"]) == 1
    assert fields["red_flags"][0]["resolved"] is False


def test_empty_requirements_produce_empty_lists_not_none() -> None:
    fields = to_job_fields(StructuredJD(title="Intern"))
    assert fields["must_have_skills"] == []
    assert fields["nice_to_have_skills"] == []


def test_slugify() -> None:
    assert slugify("Senior Backend Engineer") == "senior-backend-engineer"
    assert slugify("AI/ML Engineer (Remote)") == "ai-ml-engineer-remote"
    assert slugify("   ") == "role"
    assert slugify("Backend Engineer", suffix="a1b2") == "backend-engineer-a1b2"
