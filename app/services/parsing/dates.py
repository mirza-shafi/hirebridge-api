"""Date normalization for CV date ranges.

Local CVs write the same range half a dozen ways — `Jan'23 - now`, `01/2023 – Present`,
`2023-current`, `March 2023 to date`. The parser stores ISO dates and keeps the original
string for display; anything unrecognized stays None rather than being guessed
(docs/03-agent-specs.md §1: never infer a fact that is not written).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTHS: dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

PRESENT_TOKENS = frozenset(
    {"present", "now", "current", "currently", "ongoing", "to date", "till date",
     "till now", "continuing", "date"}
)

RANGE_SEPARATORS = re.compile(r"\s*(?:--|–|—|-|\bto\b|\bthrough\b|\buntil\b)\s*", re.I)

_MONTH_YEAR = re.compile(
    r"^(?P<month>[a-z]+)\.?\s*[''’]?\s*(?P<year>\d{2,4})$", re.I
)
_NUMERIC = re.compile(r"^(?P<a>\d{1,4})\s*[/.\-]\s*(?P<b>\d{2,4})$")
_YEAR_ONLY = re.compile(r"^(?P<year>(?:19|20)\d{2})$")


def _expand_year(value: int) -> int:
    if value >= 100:
        return value
    # A two-digit year in a CV is this century unless that lands in the future.
    candidate = 2000 + value
    return candidate if candidate <= date.today().year else 1900 + value


def parse_token(token: str) -> date | None:
    """Parse one side of a range. Returns the first day of the month when no day is given."""
    text = token.strip().strip(",.").lower()
    if not text:
        return None

    if match := _YEAR_ONLY.match(text):
        return date(int(match["year"]), 1, 1)

    if match := _MONTH_YEAR.match(text):
        month = MONTHS.get(match["month"].lower())
        if month:
            return date(_expand_year(int(match["year"])), month, 1)

    if match := _NUMERIC.match(text):
        a, b = int(match["a"]), int(match["b"])
        # 2023-05 vs 05/2023 — a four-digit component is unambiguously the year.
        if a > 12:
            return date(_expand_year(a), b, 1) if 1 <= b <= 12 else None
        if b > 12:
            return date(_expand_year(b), a, 1) if 1 <= a <= 12 else None
        # Both ≤ 12 is genuinely ambiguous (03/04). Refuse rather than guess.
        return None

    return None


def is_present(token: str) -> bool:
    return token.strip().strip(",.").lower() in PRESENT_TOKENS


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date | None
    end: date | None
    is_current: bool
    raw: str

    @property
    def months(self) -> int | None:
        if self.start is None:
            return None
        end = self.end or date.today()
        return max(0, (end.year - self.start.year) * 12 + end.month - self.start.month)


def parse_range(raw: str) -> DateRange:
    text = raw.strip()
    parts = [p for p in RANGE_SEPARATORS.split(text) if p.strip()]

    if len(parts) == 1:
        single = parse_token(parts[0])
        return DateRange(start=single, end=single, is_current=False, raw=raw)

    if len(parts) >= 2:
        start = parse_token(parts[0])
        tail = parts[-1]
        if is_present(tail):
            return DateRange(start=start, end=None, is_current=True, raw=raw)
        return DateRange(start=start, end=parse_token(tail), is_current=False, raw=raw)

    return DateRange(start=None, end=None, is_current=False, raw=raw)
