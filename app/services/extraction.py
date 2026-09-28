"""Text extraction from uploaded CVs.

Layout matters more than it looks: a two-column CV read as plain text interleaves the two
columns and produces a profile full of bullets attached to the wrong employer. Extractors are
resolved lazily so the module imports without the optional dependencies present.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import BinaryIO

log = logging.getLogger("hirebridge.extraction")

# Below this, the document is almost certainly a scanned image rather than a text PDF.
MIN_USEFUL_CHARS = 200

SUPPORTED_MIMES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
}


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    text: str
    page_count: int
    needs_ocr: bool
    warnings: list[str]

    @property
    def is_usable(self) -> bool:
        return len(self.text.strip()) >= MIN_USEFUL_CHARS


class UnsupportedDocument(ValueError):
    pass


def extract(stream: BinaryIO, mime: str) -> ExtractionResult:
    kind = SUPPORTED_MIMES.get(mime)
    if kind is None:
        raise UnsupportedDocument(f"Cannot read {mime}. Upload a PDF, DOCX, or plain text CV.")
    if kind == "pdf":
        return _extract_pdf(stream)
    if kind == "docx":
        return _extract_docx(stream)
    return ExtractionResult(
        text=stream.read().decode("utf-8", errors="replace"),
        page_count=1, needs_ocr=False, warnings=[],
    )


def _extract_pdf(stream: BinaryIO) -> ExtractionResult:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pdfplumber is required to read PDF CVs.") from exc

    warnings: list[str] = []
    parts: list[str] = []

    with pdfplumber.open(stream) as pdf:
        pages = pdf.pages
        for index, page in enumerate(pages, start=1):
            # layout=True preserves column structure, which keeps bullets with their employer.
            text = page.extract_text(layout=True) or ""
            if not text.strip():
                warnings.append(f"Page {index} contained no extractable text.")
            parts.append(text)

    joined = "\n\n".join(parts).strip()
    needs_ocr = len(joined) < MIN_USEFUL_CHARS
    if needs_ocr:
        warnings.append(
            "This looks like a scanned image rather than a text PDF. "
            "We can run OCR, or you can enter your details manually."
        )
    return ExtractionResult(joined, len(pages), needs_ocr, warnings)


def _extract_docx(stream: BinaryIO) -> ExtractionResult:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("python-docx is required to read DOCX CVs.") from exc

    document = docx.Document(stream)
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    # Many CVs lay out contact blocks and skills in tables; skipping them loses real content.
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append("  ".join(cells))

    joined = "\n".join(parts).strip()
    return ExtractionResult(joined, 1, len(joined) < MIN_USEFUL_CHARS, [])
