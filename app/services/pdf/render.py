"""Render a tailored CV to PDF.

HTML + CSS rather than a drawing API: two templates need to be iterated on by eye, and
CSS is the medium for that. The cost is system libraries in the image (ADR-0008).

WeasyPrint is imported lazily so `layout.py` and the template rendering stay testable
without the toolchain installed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.schemas.resume import TailoredResume
from app.services.pdf.ats import AtsReport, check
from app.services.pdf.layout import RenderModel, build_render_model

log = logging.getLogger("hirebridge.pdf")

TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATES = {"modern": "modern.html", "classic": "classic.html"}
DEFAULT_TEMPLATE = "modern"


class UnknownTemplate(ValueError):
    pass


_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),   # CV text is user content
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True, slots=True)
class RenderedPdf:
    content: bytes
    template: str
    ats: AtsReport


def render_html(model: RenderModel, *, template: str = DEFAULT_TEMPLATE) -> str:
    if template not in TEMPLATES:
        raise UnknownTemplate(f"Unknown CV template {template!r}. Choose from {sorted(TEMPLATES)}.")
    base_css = (TEMPLATE_DIR / "base.css").read_text()
    return _env.get_template(TEMPLATES[template]).render(model=model, base_css=base_css)


def render_pdf(
    resume: TailoredResume,
    *,
    full_name: str,
    contact: list[str] | None = None,
    template: str = DEFAULT_TEMPLATE,
) -> RenderedPdf:
    model = build_render_model(resume, full_name=full_name, contact=contact)
    html = render_html(model, template=template)

    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "WeasyPrint is required to render CVs. On Debian-based images it also needs "
            "libpango and libharfbuzz — see the Dockerfile."
        ) from exc

    content: bytes = HTML(string=html).write_pdf()

    expected = " ".join(line for section in model.sections for line in section.lines)
    report = check(content, expected_text=f"{model.full_name} {expected}")
    if not report.is_machine_readable:
        # Not fatal — the candidate still gets their CV — but it is a defect worth alerting on.
        log.warning(
            "Rendered CV may not parse cleanly: coverage=%.2f problems=%s",
            report.coverage,
            report.problems,
        )

    return RenderedPdf(content=content, template=template, ats=report)
