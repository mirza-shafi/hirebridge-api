"""Turn a TailoredResume into the shape a CV template needs.

Pure: no rendering engine, no I/O. The structure decisions live here so they can be tested
without installing a PDF toolchain (docs/01-architecture.md §12).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.resume import TailoredLine, TailoredResume

# The order a recruiter expects, and the order an ATS parser handles best.
SECTION_ORDER = [
    "summary",
    "experience",
    "projects",
    "education",
    "skills",
    "certifications",
    "awards",
    "publications",
    "languages",
]

SECTION_TITLES = {
    "summary": "Summary",
    "experience": "Experience",
    "projects": "Projects",
    "education": "Education",
    "skills": "Skills",
    "certifications": "Certifications",
    "awards": "Awards",
    "publications": "Publications",
    "languages": "Languages",
}


@dataclass(frozen=True, slots=True)
class RenderSection:
    key: str
    title: str
    lines: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RenderModel:
    full_name: str
    headline: str | None
    contact: list[str]
    sections: list[RenderSection]

    @property
    def total_lines(self) -> int:
        return sum(len(s.lines) for s in self.sections)


def _section_key(line: TailoredLine) -> str:
    return (line.section or "experience").strip().lower()


def build_render_model(
    resume: TailoredResume,
    *,
    full_name: str,
    contact: list[str] | None = None,
) -> RenderModel:
    """Group lines into sections, in a fixed order.

    Headings from the agent are dropped: the template owns section titles, so a model that
    writes "EXPERIENCE" in a heading line cannot produce a duplicate header in the document.
    """
    grouped: dict[str, list[str]] = {}
    for line in resume.lines:
        if line.is_heading or not line.text.strip():
            continue
        grouped.setdefault(_section_key(line), []).append(line.text.strip())

    ordered: list[RenderSection] = []
    for key in SECTION_ORDER:
        if lines := grouped.pop(key, None):
            ordered.append(RenderSection(key=key, title=SECTION_TITLES[key], lines=lines))

    # Anything the agent invented a section name for still appears, after the known ones.
    for key in sorted(grouped):
        ordered.append(
            RenderSection(key=key, title=key.replace("_", " ").title(), lines=grouped[key])
        )

    return RenderModel(
        full_name=full_name,
        headline=resume.headline,
        contact=[c for c in (contact or []) if c.strip()],
        sections=ordered,
    )
