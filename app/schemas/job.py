from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RequirementType = Literal["must", "nice"]
Seniority = Literal["intern", "junior", "mid", "senior", "lead", "principal"]


class Requirement(BaseModel):
    text: str = Field(description="The requirement as written in the job description.")
    type: RequirementType = Field(
        description=(
            "'must' only when the description signals it is mandatory. Default to 'nice' "
            "when unsignalled — an over-strict must-have silently sinks good candidates."
        )
    )
    skill: str | None = Field(default=None, description="The skill named, if any.")
    years: int | None = Field(default=None, description="Years demanded, if stated.")


class RedFlag(BaseModel):
    """Phrasing that would exclude qualified candidates, and is unlawful in many markets."""

    text: str = Field(description="The exact phrase from the description.")
    category: Literal[
        "gender", "age", "marital_status", "religion", "ethnicity",
        "appearance", "disability", "nationality", "other"
    ]
    explanation: str = Field(description="Why this phrasing is a problem, in one sentence.")
    suggestion: str = Field(description="A neutral rewrite the employer can use instead.")
    resolved: bool = False


class StructuredJD(BaseModel):
    title: str
    seniority: Seniority | None = Field(
        default=None,
        description=(
            "Infer from the responsibilities, not only the title. A 'Senior' title with "
            "one-year requirements is a real signal worth surfacing."
        ),
    )
    employment_type: Literal["full_time", "part_time", "contract", "internship"] | None = None
    work_mode: Literal["onsite", "hybrid", "remote"] | None = None
    location: str | None = None

    responsibilities: list[str] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    team_context: str | None = None

    min_years: int | None = None
    max_years: int | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = None

    red_flags: list[RedFlag] = Field(default_factory=list)

    @property
    def must_have_skills(self) -> list[str]:
        return [r.skill for r in self.requirements if r.type == "must" and r.skill]

    @property
    def nice_to_have_skills(self) -> list[str]:
        return [r.skill for r in self.requirements if r.type == "nice" and r.skill]
