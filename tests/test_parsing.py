from __future__ import annotations

from datetime import date

import pytest

from app.services.parsing.dates import parse_range, parse_token
from app.services.parsing.skills import canonical, extract_known_skills


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PostgreSQL", "postgres"),
        ("postgres", "postgres"),
        ("Postgre SQL", "postgres"),
        ("Next.js", "nextjs"),
        ("NEXT JS", "nextjs"),
        ("Retrieval Augmented Generation", "rag"),
        ("RAG", "rag"),
        ("K8s", "kubernetes"),
        ("CI/CD", "ci_cd"),
        ("RESTful APIs", "rest_api"),
        ("Svelte", "svelte"),  # unknown skills still normalize consistently
    ],
)
def test_canonical_skill_names(raw: str, expected: str) -> None:
    assert canonical(raw) == expected


def test_jd_and_cv_spellings_converge() -> None:
    assert canonical("PostgreSQL") == canonical("Postgres")
    assert canonical("Next.js") == canonical("nextjs")


def test_extract_skills_from_a_bullet() -> None:
    found = extract_known_skills("Built a RAG chatbot with FastAPI and Postgres on AWS")
    assert {"rag", "fastapi", "postgres", "aws"} <= found


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Jan 2023", date(2023, 1, 1)),
        ("Jan'23", date(2023, 1, 1)),
        ("January 2023", date(2023, 1, 1)),
        ("01/2023", date(2023, 1, 1)),
        ("2023-05", date(2023, 5, 1)),
        ("2019", date(2019, 1, 1)),
    ],
)
def test_parse_single_dates(raw: str, expected: date) -> None:
    assert parse_token(raw) == expected


def test_ambiguous_numeric_date_is_refused_not_guessed() -> None:
    # 03/04 could be March 2004 or April 2003. Guessing would fabricate a fact.
    assert parse_token("03/04") is None


@pytest.mark.parametrize(
    "raw",
    [
        "Jan 2023 - Present",
        "01/2023 – now",
        "January 2023 to date",
        "Jan'23-current",
        "Jan 2023 — ongoing",
    ],
)
def test_current_role_variants(raw: str) -> None:
    result = parse_range(raw)
    assert result.start == date(2023, 1, 1)
    assert result.is_current is True
    assert result.end is None


def test_closed_range() -> None:
    result = parse_range("March 2021 - August 2023")
    assert result.start == date(2021, 3, 1)
    assert result.end == date(2023, 8, 1)
    assert result.is_current is False
    assert result.months == 29


def test_unparseable_range_returns_nothing_rather_than_a_guess() -> None:
    result = parse_range("sometime last year")
    assert result.start is None and result.end is None
