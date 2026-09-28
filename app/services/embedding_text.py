"""What actually gets embedded.

Embedding a whole CV verbatim buries the signal: contact blocks, section headers and dates
are noise, and the same boilerplate appears in every CV. These builders assemble a compact
text from the fields that carry meaning.

Identity fields are excluded — not because the vector would leak a name, but because a name
that correlates with region or religion becomes a similarity signal, which is exactly the
proxy discrimination product rule 7 exists to prevent.
"""

from __future__ import annotations

from typing import Any


def profile_embedding_text(
    *,
    headline: str | None,
    summary: str | None,
    fact_rows: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    if headline:
        parts.append(headline)
    if summary:
        parts.append(summary)

    skills: set[str] = set()
    for row in fact_rows:
        payload = row.get("payload") or {}
        kind = row.get("kind")

        if kind == "experience":
            title = payload.get("title") or ""
            parts.append(f"{title} at {payload.get('company', '')}".strip())
            parts.extend(b["text"] for b in payload.get("bullets", []) if b.get("text"))
            skills |= set(payload.get("tech") or [])
        elif kind == "project":
            parts.append(f"{payload.get('name', '')}: {payload.get('description') or ''}".strip())
            skills |= set(payload.get("tech") or [])
        elif kind == "education":
            parts.append(
                f"{payload.get('degree') or ''} {payload.get('field') or ''}".strip()
            )
        elif kind in {"skill", "certification"}:
            if name := payload.get("name"):
                parts.append(str(name))

    if skills:
        parts.append("Skills: " + ", ".join(sorted(skills)))

    return "\n".join(p for p in parts if p.strip())


def job_embedding_text(
    *,
    title: str,
    seniority: str | None,
    structured: dict[str, Any] | None,
    must_have: list[str] | None,
    nice_to_have: list[str] | None,
) -> str:
    """Mirror the profile's shape so the two vectors are comparable.

    Benefits and company boilerplate are deliberately excluded: "competitive salary" and
    "dynamic team" appear in every posting and only add noise to the similarity score.
    """
    parts: list[str] = [title]
    if seniority:
        parts.append(f"Seniority: {seniority}")

    structured = structured or {}
    parts.extend(structured.get("responsibilities") or [])
    parts.extend(
        r["text"] for r in (structured.get("requirements") or []) if r.get("text")
    )
    if must_have:
        parts.append("Required skills: " + ", ".join(sorted(must_have)))
    if nice_to_have:
        parts.append("Preferred skills: " + ", ".join(sorted(nice_to_have)))

    return "\n".join(p for p in parts if p and p.strip())
