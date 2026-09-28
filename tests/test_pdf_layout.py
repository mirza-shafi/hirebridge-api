"""Layout and template rendering. No PDF toolchain required."""

from __future__ import annotations

import pytest

from app.schemas.resume import TailoredLine, TailoredResume
from app.services.pdf.layout import build_render_model
from app.services.pdf.render import TEMPLATE_DIR, UnknownTemplate, render_html


def _line(text: str, section: str, heading: bool = False) -> TailoredLine:
    return TailoredLine(
        line_id=text[:6], section=section, text=text,
        source_fact_ids=[] if heading else ["f1"], is_heading=heading,
    )


RESUME = TailoredResume(
    headline="Backend Developer",
    lines=[
        _line("EXPERIENCE", "experience", heading=True),
        _line("Built a retrieval chatbot at Autofy", "experience"),
        _line("Migrated a REST API to async handlers", "experience"),
        _line("B.Sc. Computer Science, BRAC University", "education"),
        _line("Python, FastAPI, Postgres", "skills"),
        _line("Experienced backend developer", "summary"),
    ],
)


def test_sections_are_ordered_for_a_recruiter_and_a_parser() -> None:
    model = build_render_model(RESUME, full_name="Mirza")
    assert [s.key for s in model.sections] == ["summary", "experience", "education", "skills"]


def test_agent_headings_are_dropped_so_titles_are_not_duplicated() -> None:
    model = build_render_model(RESUME, full_name="Mirza")
    experience = next(s for s in model.sections if s.key == "experience")
    assert "EXPERIENCE" not in experience.lines
    assert len(experience.lines) == 2


def test_unknown_sections_still_appear() -> None:
    resume = TailoredResume(lines=[_line("Volunteer work", "community")])
    model = build_render_model(resume, full_name="Mirza")
    assert [s.title for s in model.sections] == ["Community"]


def test_empty_lines_are_skipped() -> None:
    resume = TailoredResume(lines=[_line("  ", "experience"), _line("Real line", "experience")])
    model = build_render_model(resume, full_name="Mirza")
    assert model.total_lines == 1


@pytest.mark.parametrize("template", ["modern", "classic"])
def test_templates_render_the_content(template: str) -> None:
    model = build_render_model(
        RESUME, full_name="Mirza Md Shafi Uddin", contact=["dhaka", "github.com/mirza-shafi"]
    )
    html = render_html(model, template=template)

    assert "Mirza Md Shafi Uddin" in html
    assert "Built a retrieval chatbot at Autofy" in html
    assert "Experience" in html and "Education" in html


def test_cv_text_is_escaped() -> None:
    """CV content is user input and reaches a template engine."""
    resume = TailoredResume(lines=[_line("Built <script>alert(1)</script> tooling", "experience")])
    html = render_html(build_render_model(resume, full_name="A & B <test>"))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "A &amp; B" in html


def test_templates_use_no_tables() -> None:
    """Tables carrying content are the classic reason a CV parses into nonsense."""
    model = build_render_model(RESUME, full_name="Mirza")
    for template in ("modern", "classic"):
        html = render_html(model, template=template)
        assert "<table" not in html.lower()


def test_unknown_template_is_rejected() -> None:
    model = build_render_model(RESUME, full_name="Mirza")
    with pytest.raises(UnknownTemplate, match="modern"):
        render_html(model, template="fancy")


def test_contact_separator_is_real_text_not_generated_content() -> None:
    """Regression: the separator used to be a CSS `::before` pseudo-element.

    Generated content is invisible to PDF text extraction, so an ATS read the contact line
    as "Dhaka, Bangladeshgithub.com/mirza-shafi" — one token, with the fields lost.
    """
    model = build_render_model(
        RESUME, full_name="Mirza", contact=["Dhaka", "github.com/mirza-shafi", "mirzashafi.com"]
    )
    for template in ("modern", "classic"):
        html = render_html(model, template=template)
        assert html.count("\u00b7") == 2, "separators must be in the markup, one between each pair"

    css = (TEMPLATE_DIR / "base.css").read_text()
    assert "content:" not in css, "no CSS generated content — extraction cannot see it"
