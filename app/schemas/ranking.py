from __future__ import annotations

from pydantic import BaseModel, Field


class MatchedRequirement(BaseModel):
    requirement: str = Field(description="The job requirement, as the posting words it.")
    fact_id: str = Field(
        description="The candidate fact that evidences it. The UI links this to the CV line."
    )
    evidence: str = Field(description="The specific wording from the CV that shows it.")


class Justification(BaseModel):
    """Explains a score that was already computed. It does not produce one."""

    summary: str = Field(
        description=(
            "Two or three sentences on why this candidate scored where they did. State "
            "absence of evidence, never a judgement of the person."
        )
    )
    matched: list[MatchedRequirement] = Field(default_factory=list)
    missing: list[str] = Field(
        default_factory=list,
        description="Requirements with no supporting evidence in the CV.",
    )
    notable: list[str] = Field(
        default_factory=list,
        description="Anything a recruiter would want flagged — a career change, an unusual "
        "combination of skills, a long gap the CV itself explains.",
    )
