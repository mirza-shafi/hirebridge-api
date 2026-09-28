"""Build the grounding set the tailoring agent is allowed to draw from.

Each addressable unit becomes its own `SourceFact`: the role as a whole (`f1`) and every
bullet inside it (`f1#b1`). The agent cites the narrowest unit it used, and the validator
checks against exactly that unit — so a metric in one bullet cannot silently license a claim
rewritten from another.
"""

from __future__ import annotations

from typing import Any

from app.schemas.resume import SourceFact


def build_source_facts(fact_rows: list[dict[str, Any]]) -> list[SourceFact]:
    facts: list[SourceFact] = []

    for row in fact_rows:
        fact_id = str(row["id"])
        kind = str(row.get("kind", ""))
        payload: dict[str, Any] = row.get("payload") or {}
        start, end = row.get("start_date"), row.get("end_date")

        summary = _summarise(kind, payload)
        skills = list(payload.get("tech") or [])
        bullets = payload.get("bullets") or []

        facts.append(
            SourceFact(
                fact_id=fact_id,
                kind=kind,
                text=" ".join(
                    [summary, *(b.get("text", "") for b in bullets)]
                ).strip(),
                skills=skills,
                start_date=start,
                end_date=end,
            )
        )

        for bullet in bullets:
            if not (text := bullet.get("text")):
                continue
            facts.append(
                SourceFact(
                    fact_id=f"{fact_id}#{bullet.get('id', '')}",
                    kind=kind,
                    # The role line stays attached: a bullet alone often lacks the employer
                    # and dates the validator needs for context.
                    text=f"{summary} {text}".strip(),
                    skills=skills,
                    start_date=start,
                    end_date=end,
                )
            )

    return facts


def _summarise(kind: str, payload: dict[str, Any]) -> str:
    if kind == "experience":
        title = payload.get("title") or ""
        company = payload.get("company") or ""
        return f"{title} at {company}".strip(" at ").strip()
    if kind == "education":
        return " ".join(
            str(payload.get(k) or "") for k in ("degree", "field", "institution")
        ).strip()
    if kind == "project":
        return f"{payload.get('name') or ''}: {payload.get('description') or ''}".strip(": ")
    return str(payload.get("name") or payload.get("detail") or "")


def render_for_prompt(facts: list[SourceFact]) -> str:
    """Render the grounding set with its ids visible, so the model can cite them."""
    lines: list[str] = []
    for fact in facts:
        window = ""
        if fact.start_date:
            window = f" [{fact.start_date.isoformat()} to " + (
                fact.end_date.isoformat() if fact.end_date else "present"
            ) + "]"
        lines.append(f"[{fact.fact_id}] ({fact.kind}){window} {fact.text}")
    return "\n".join(lines)
