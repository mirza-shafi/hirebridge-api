"""Machine-readability check for a rendered CV.

A CV that a human likes and a parser cannot read is worse than useless — it fails silently,
and the candidate never learns why they heard nothing back. This runs against the produced
PDF, not the template, because the failure modes are in the output.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AtsReport:
    extractable_chars: int
    expected_chars: int
    page_count: int
    problems: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        if self.expected_chars == 0:
            return 1.0
        return min(1.0, self.extractable_chars / self.expected_chars)

    @property
    def is_machine_readable(self) -> bool:
        return not self.problems and self.coverage >= 0.9


def check(pdf_bytes: bytes, *, expected_text: str, max_pages: int = 3) -> AtsReport:
    """Extract the text back out and confirm it survived rendering."""
    try:
        import pdfplumber
    except ImportError:  # pragma: no cover
        return AtsReport(0, len(expected_text), 0, ["pdfplumber is not installed."])

    import io

    problems: list[str] = []
    extracted: list[str] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = pdf.pages
        for page in pages:
            extracted.append(page.extract_text() or "")
            # A table carrying content reorders unpredictably in most parsers.
            if page.find_tables():
                problems.append("The layout uses tables, which many CV parsers misread.")

        page_count = len(pages)

    if page_count > max_pages:
        problems.append(f"{page_count} pages; keep a CV to {max_pages} or fewer.")
    if page_count == 0:
        problems.append("The document has no pages.")

    text = " ".join(extracted)
    normalised = "".join(text.split())
    expected = "".join(expected_text.split())

    report = AtsReport(
        extractable_chars=len(normalised),
        expected_chars=len(expected),
        page_count=page_count,
        problems=problems,
    )
    if report.coverage < 0.9:
        problems.append(
            "Less text was recoverable from the PDF than went into it — "
            "a parser would miss content."
        )
        return AtsReport(len(normalised), len(expected), page_count, problems)

    return report
