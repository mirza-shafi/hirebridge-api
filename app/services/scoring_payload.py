"""Scoring input construction — release gate.

Product rule 7 (docs/00-product-brief.md §8): protected attributes are never features.

This is an **allowlist**, not a denylist. A denylist fails open — the day someone adds
`father_name` to a profile payload, a denylist silently starts scoring on it. An allowlist
fails closed: a new field is invisible to scoring until somebody deliberately admits it.

Nothing else in the codebase may assemble a scoring payload. If a ranking or justification
agent needs a field, it is added here, in a commit whose diff makes that decision visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.resume import SourceFact
from app.services.parsing.skills import canonical

# Fields permitted to influence a score or a justification.
ALLOWED_SCORING_FIELDS: frozenset[str] = frozenset(
    {
        "years_experience",
        "skills",
        "job_titles",
        "employers",
        "education_level",
        "field_of_study",
        "certifications",
        "project_descriptions",
        "languages_spoken",
        "location_city",  # work authorization and commute only
    }
)

# Never reaches a scoring model. Listed explicitly so the intent is documented and so the
# gate test can assert on it directly — the allowlist is what enforces it.
NEVER_SCORED: frozenset[str] = frozenset(
    {
        "full_name", "first_name", "last_name", "email", "phone", "photo", "photo_url",
        "date_of_birth", "dob", "age", "gender", "sex", "marital_status", "religion",
        "nationality", "father_name", "mother_name", "guardian_name", "address",
        "postal_code", "nid", "national_id", "passport_number", "blood_group",
        "profile_picture", "linkedin_photo", "caste", "disability", "veteran_status",
    }
)

_EXPERIENCE_KINDS = frozenset({"experience"})
_PROJECT_KINDS = frozenset({"project"})
_EDUCATION_KINDS = frozenset({"education"})
_CERTIFICATION_KINDS = frozenset({"certification"})
_LANGUAGE_KINDS = frozenset({"language"})


class ScoringPayloadError(RuntimeError):
    """Raised when a payload would carry a field outside the allowlist."""


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    """Everything the ranking pipeline is allowed to know about a person."""

    years_experience: float | None
    location_city: str | None
    skills: list[str]
    job_titles: list[str]
    employers: list[str]
    education_level: list[str]
    field_of_study: list[str]
    certifications: list[str]
    project_descriptions: list[str]
    languages_spoken: list[str]

    def as_payload(self) -> dict[str, Any]:
        return {
            "years_experience": self.years_experience,
            "location_city": self.location_city,
            "skills": self.skills,
            "job_titles": self.job_titles,
            "employers": self.employers,
            "education_level": self.education_level,
            "field_of_study": self.field_of_study,
            "certifications": self.certifications,
            "project_descriptions": self.project_descriptions,
            "languages_spoken": self.languages_spoken,
        }


def _collect(payload: dict[str, Any], *keys: str) -> list[str]:
    out: list[str] = []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            out.append(value.strip())
        elif isinstance(value, list):
            out.extend(v.strip() for v in value if isinstance(v, str) and v.strip())
    return out


def build_candidate_snapshot(
    *,
    facts: list[SourceFact],
    raw_facts: list[dict[str, Any]] | None = None,
    years_experience: float | None = None,
    location_city: str | None = None,
) -> CandidateSnapshot:
    """Assemble the only view of a candidate that scoring is permitted to see.

    Reads named fields out of each fact's payload rather than passing the payload through,
    so a parser that starts emitting `father_name` cannot leak it into a score.
    """
    skills: set[str] = set()
    titles: list[str] = []
    employers: list[str] = []
    education: list[str] = []
    fields_of_study: list[str] = []
    certifications: list[str] = []
    projects: list[str] = []
    languages: list[str] = []

    for fact in facts:
        skills |= {c for s in fact.skills if (c := canonical(s))}

    for raw in raw_facts or []:
        kind = str(raw.get("kind", ""))
        payload = raw.get("payload") or {}
        if not isinstance(payload, dict):
            continue

        if kind in _EXPERIENCE_KINDS:
            titles.extend(_collect(payload, "title"))
            employers.extend(_collect(payload, "company", "employer"))
        elif kind in _EDUCATION_KINDS:
            education.extend(_collect(payload, "degree", "level"))
            fields_of_study.extend(_collect(payload, "field", "major", "subject"))
        elif kind in _CERTIFICATION_KINDS:
            certifications.extend(_collect(payload, "name", "title"))
        elif kind in _PROJECT_KINDS:
            projects.extend(_collect(payload, "description", "summary"))
        elif kind in _LANGUAGE_KINDS:
            languages.extend(_collect(payload, "name", "language"))

        skills |= {c for s in _collect(payload, "tech", "skills") if (c := canonical(s))}

    return CandidateSnapshot(
        years_experience=years_experience,
        location_city=location_city,
        skills=sorted(skills),
        job_titles=titles,
        employers=employers,
        education_level=education,
        field_of_study=fields_of_study,
        certifications=certifications,
        project_descriptions=projects,
        languages_spoken=languages,
    )


def assert_allowlisted(payload: dict[str, Any]) -> None:
    """Fail loudly rather than score on something that should never have been included."""
    if extra := set(payload) - ALLOWED_SCORING_FIELDS:
        raise ScoringPayloadError(
            "Scoring payload carries fields outside the allowlist: "
            f"{', '.join(sorted(extra))}. Add them to ALLOWED_SCORING_FIELDS deliberately, "
            "or keep them out of scoring."
        )


def build_scoring_payload(**kwargs: Any) -> dict[str, Any]:
    """The only supported way to produce scoring input."""
    payload = build_candidate_snapshot(**kwargs).as_payload()
    assert_allowlisted(payload)
    return payload
