from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class SourceFact(BaseModel):
    """A fact from the candidate's profile, flattened for grounding checks."""

    fact_id: str
    kind: str
    text: str
    skills: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None


class TailoredLine(BaseModel):
    """One content line of a generated CV.

    `source_fact_ids` is not optional by convention — the validator rejects any content
    line without one (docs/00-product-brief.md §8 rule 1).
    """

    line_id: str
    section: str
    text: str
    source_fact_ids: list[str] = Field(default_factory=list)
    is_heading: bool = False


class TailoredResume(BaseModel):
    headline: str | None = None
    lines: list[TailoredLine]
