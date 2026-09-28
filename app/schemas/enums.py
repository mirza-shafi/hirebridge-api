"""Plain enums with no framework imports.

Kept dependency-free on purpose: the fabrication validator is a release gate, and it must be
importable and testable without a database, a Redis connection, or a populated environment.
"""

from __future__ import annotations

import enum


class ValidatorStatus(str, enum.Enum):
    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    FAILED = "failed"
    NOT_REQUIRED = "not_required"


class Severity(str, enum.Enum):
    HARD = "hard"
    SOFT = "soft"


class FactKind(str, enum.Enum):
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILL = "skill"
    PROJECT = "project"
    CERTIFICATION = "certification"
    AWARD = "award"
    PUBLICATION = "publication"
    LANGUAGE = "language"


class FactSource(str, enum.Enum):
    PARSED_RESUME = "parsed_resume"
    USER_ENTERED = "user_entered"
    USER_EDITED = "user_edited"
