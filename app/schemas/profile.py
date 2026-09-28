from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FactKindLiteral = Literal[
    "experience", "education", "skill", "project",
    "certification", "award", "publication", "language",
]


class ParsedBullet(BaseModel):
    id: str = Field(description="Stable id, unique within the fact, e.g. 'b1'.")
    text: str


class ParsedExperience(BaseModel):
    company: str
    title: str | None = None
    employment_type: str | None = None
    location: str | None = None
    date_range_raw: str | None = Field(
        default=None, description="The dates exactly as written. Do not reformat them."
    )
    bullets: list[ParsedBullet] = Field(default_factory=list)
    tech: list[str] = Field(default_factory=list)


class ParsedEducation(BaseModel):
    institution: str
    degree: str | None = None
    field: str | None = None
    date_range_raw: str | None = None
    result: str | None = None


class ParsedProject(BaseModel):
    name: str
    description: str | None = None
    tech: list[str] = Field(default_factory=list)
    url: str | None = None


class ParsedSimpleItem(BaseModel):
    name: str
    detail: str | None = None
    date_raw: str | None = None


class ParsedContact(BaseModel):
    """Captured for the CV header only.

    Never reaches a scoring model — `app/services/scoring_payload.py` is an allowlist and
    none of these fields are on it.
    """

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location_city: str | None = None
    links: list[str] = Field(default_factory=list)


class ParsedFact(BaseModel):
    kind: FactKindLiteral
    confidence: float = Field(
        ge=0.0, le=1.0,
        description=(
            "How certain you are this reading is correct. Below 0.7 asks the user to "
            "confirm it, which is cheap. A confident wrong answer is not."
        ),
    )
    experience: ParsedExperience | None = None
    education: ParsedEducation | None = None
    project: ParsedProject | None = None
    item: ParsedSimpleItem | None = Field(
        default=None, description="For skill, certification, award, publication, language."
    )


class ParsedProfile(BaseModel):
    contact: ParsedContact
    headline: str | None = None
    summary: str | None = None
    facts: list[ParsedFact] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(
        default_factory=list,
        description="Anything unreadable or ambiguous, stated plainly for the user.",
    )
