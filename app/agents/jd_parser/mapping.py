"""Pure JD -> Job column mapping.

Kept free of SQLAlchemy and the agent runner so it is testable without a database
driver — the transformation is where the bugs live, and it should be the cheapest
part of the pipeline to test.
"""

from __future__ import annotations

import re
from typing import Any

from app.schemas.job import StructuredJD
from app.services.parsing.skills import canonical


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(title: str, *, suffix: str | None = None) -> str:
    base = _SLUG_STRIP.sub("-", title.strip().lower()).strip("-") or "role"
    return f"{base}-{suffix}" if suffix else base


def to_job_fields(parsed: StructuredJD) -> dict[str, Any]:
    """Map the parsed structure onto Job columns.

    Skill names are canonicalised here, at the boundary — the prompt deliberately leaves them
    as written so the model is not asked to do vocabulary work it will do inconsistently.
    """
    return {
        "title": parsed.title,
        "seniority": parsed.seniority,
        "employment_type": parsed.employment_type,
        "work_mode": parsed.work_mode,
        "location": parsed.location,
        "salary_min": parsed.salary_min,
        "salary_max": parsed.salary_max,
        "currency": parsed.currency,
        "min_years": parsed.min_years,
        "max_years": parsed.max_years,
        "must_have_skills": sorted({canonical(s) for s in parsed.must_have_skills if s}),
        "nice_to_have_skills": sorted({canonical(s) for s in parsed.nice_to_have_skills if s}),
        "red_flags": [flag.model_dump() for flag in parsed.red_flags],
        "description_structured": {
            "responsibilities": parsed.responsibilities,
            "requirements": [r.model_dump() for r in parsed.requirements],
            "benefits": parsed.benefits,
            "team_context": parsed.team_context,
        },
    }
