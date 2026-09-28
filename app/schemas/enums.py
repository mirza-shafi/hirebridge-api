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


class ApplicationStage(str, enum.Enum):
    NEW = "new"
    SHORTLISTED = "shortlisted"
    INTERVIEW = "interview"
    OFFER = "offer"
    HIRED = "hired"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"

    @property
    def is_terminal(self) -> bool:
        return self in {
            ApplicationStage.HIRED,
            ApplicationStage.REJECTED,
            ApplicationStage.WITHDRAWN,
        }


# Forward progress, plus rejection from anywhere and withdrawal by the candidate.
# Deliberately explicit: a stage change is a decision about a person, and the audit trail
# is only meaningful if the transitions are constrained.
ALLOWED_TRANSITIONS: dict[ApplicationStage, frozenset[ApplicationStage]] = {
    ApplicationStage.NEW: frozenset(
        {ApplicationStage.SHORTLISTED, ApplicationStage.INTERVIEW,
         ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN}
    ),
    ApplicationStage.SHORTLISTED: frozenset(
        {ApplicationStage.INTERVIEW, ApplicationStage.OFFER, ApplicationStage.NEW,
         ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN}
    ),
    ApplicationStage.INTERVIEW: frozenset(
        {ApplicationStage.OFFER, ApplicationStage.SHORTLISTED,
         ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN}
    ),
    ApplicationStage.OFFER: frozenset(
        {ApplicationStage.HIRED, ApplicationStage.INTERVIEW,
         ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN}
    ),
    ApplicationStage.HIRED: frozenset(),
    ApplicationStage.REJECTED: frozenset({ApplicationStage.NEW}),  # reversible: people err
    ApplicationStage.WITHDRAWN: frozenset(),
}


def can_transition(current: ApplicationStage, target: ApplicationStage) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())
