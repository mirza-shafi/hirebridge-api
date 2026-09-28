"""Pure ParsedProfile -> profile_facts row mapping.

Free of SQLAlchemy and the runner on purpose: this is where a parsing regression would
actually show up, so it must be trivial to test.
"""

from __future__ import annotations

from typing import Any

from app.schemas.enums import FactKind
from app.schemas.profile import ParsedFact, ParsedProfile
from app.services.parsing.dates import parse_range
from app.services.parsing.skills import canonical

LOW_CONFIDENCE = 0.7


def to_fact_rows(parsed: ParsedProfile) -> list[dict[str, Any]]:
    """Flatten the parse into `profile_facts` rows.

    Dates are normalised here rather than in the prompt: a deterministic parser handles local
    formats more reliably than a model, and it refuses ambiguous input instead of guessing
    (see `services/parsing/dates.py`).
    """
    rows: list[dict[str, Any]] = []

    for position, fact in enumerate(parsed.facts):
        payload, raw_dates = _payload_for(fact)
        if payload is None:
            continue

        span = parse_range(raw_dates) if raw_dates else None
        rows.append(
            {
                "kind": fact.kind,
                "payload": payload,
                "confidence": round(float(fact.confidence), 2),
                "verified_by_user": False,
                "start_date": span.start if span else None,
                "end_date": span.end if span else None,
                "position": position,
            }
        )
    return rows


def _payload_for(fact: ParsedFact) -> tuple[dict[str, Any] | None, str | None]:
    if fact.kind == FactKind.EXPERIENCE.value and fact.experience:
        exp = fact.experience
        return (
            {
                "company": exp.company,
                "title": exp.title,
                "employment_type": exp.employment_type,
                "location": exp.location,
                "raw_date": exp.date_range_raw,
                "bullets": [b.model_dump() for b in exp.bullets],
                "tech": sorted({canonical(t) for t in exp.tech if t}),
            },
            exp.date_range_raw,
        )

    if fact.kind == FactKind.EDUCATION.value and fact.education:
        edu = fact.education
        return (
            {
                "institution": edu.institution,
                "degree": edu.degree,
                "field": edu.field,
                "result": edu.result,
                "raw_date": edu.date_range_raw,
            },
            edu.date_range_raw,
        )

    if fact.kind == FactKind.PROJECT.value and fact.project:
        proj = fact.project
        return (
            {
                "name": proj.name,
                "description": proj.description,
                "url": proj.url,
                "tech": sorted({canonical(t) for t in proj.tech if t}),
            },
            None,
        )

    if fact.item:
        return (
            {"name": fact.item.name, "detail": fact.item.detail, "raw_date": fact.item.date_raw},
            fact.item.date_raw,
        )

    return None, None


def needs_review(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row["confidence"] < LOW_CONFIDENCE]


def completeness_score(rows: list[dict[str, Any]]) -> int:
    """A blunt 0-100. The UI names what is missing rather than showing this number alone."""
    kinds = {row["kind"] for row in rows}
    score = 0
    score += 35 if FactKind.EXPERIENCE.value in kinds else 0
    score += 20 if FactKind.EDUCATION.value in kinds else 0
    score += 15 if FactKind.SKILL.value in kinds else 0
    score += 15 if FactKind.PROJECT.value in kinds else 0
    bullets = sum(len(row["payload"].get("bullets", [])) for row in rows)
    score += min(15, bullets * 3)
    return min(100, score)
