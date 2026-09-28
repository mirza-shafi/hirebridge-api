from __future__ import annotations

import pytest

from app.schemas.enums import ApplicationStage as Stage
from app.schemas.enums import can_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (Stage.NEW, Stage.SHORTLISTED),
        (Stage.SHORTLISTED, Stage.INTERVIEW),
        (Stage.INTERVIEW, Stage.OFFER),
        (Stage.OFFER, Stage.HIRED),
    ],
)
def test_forward_progress_is_allowed(current: Stage, target: Stage) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize(
    "current",
    [Stage.NEW, Stage.SHORTLISTED, Stage.INTERVIEW, Stage.OFFER],
)
def test_rejection_is_possible_from_any_active_stage(current: Stage) -> None:
    assert can_transition(current, Stage.REJECTED)


def test_a_rejection_can_be_undone() -> None:
    """Recruiters misclick, and this is a decision about a person's livelihood."""
    assert can_transition(Stage.REJECTED, Stage.NEW)


def test_hired_and_withdrawn_are_terminal() -> None:
    assert Stage.HIRED.is_terminal and Stage.WITHDRAWN.is_terminal
    for target in Stage:
        assert not can_transition(Stage.HIRED, target)
        assert not can_transition(Stage.WITHDRAWN, target)


def test_cannot_skip_from_new_to_offer() -> None:
    assert not can_transition(Stage.NEW, Stage.OFFER)
    assert not can_transition(Stage.NEW, Stage.HIRED)
