"""RELEASE GATE — see docs/00-product-brief.md §8 rule 1.

A failure here blocks release. It is not a flaky test to skip.
"""

from __future__ import annotations

import pytest

from app.agents.errors import ValidationFailure
from app.agents.validators.fabrication import FabricationValidator
from app.schemas.enums import Severity, ValidatorStatus
from app.schemas.resume import TailoredLine, TailoredResume
from tests.agents.cv_tailor.cases import ALLOW_CASES, BLOCK_CASES, PROFILE


def _validator(entailment=None) -> FabricationValidator:
    return FabricationValidator(PROFILE, entailment=entailment)


@pytest.mark.parametrize("case", BLOCK_CASES, ids=lambda c: c.name)
async def test_adversarial_cases_are_blocked(case) -> None:
    context: dict[str, object] = {}
    with pytest.raises(ValidationFailure):
        await _validator()(case.resume(), context)

    findings = context["validator_findings"]
    assert any(f["severity"] == Severity.HARD.value for f in findings)
    if case.expect_check:
        checks = {f["check"] for f in findings}
        assert case.expect_check in checks, f"expected {case.expect_check}, got {checks}"


@pytest.mark.parametrize("case", ALLOW_CASES, ids=lambda c: c.name)
async def test_legitimate_rewrites_pass(case) -> None:
    context: dict[str, object] = {}
    status = await _validator()(case.resume(), context)
    assert status in {
        ValidatorStatus.PASSED.value,
        ValidatorStatus.PASSED_WITH_WARNINGS.value,
    }
    if case.expect_check:
        assert case.expect_check in {f["check"] for f in context["validator_findings"]}


async def test_block_rate_is_total() -> None:
    """The gate itself: every adversarial case blocked, no exceptions."""
    blocked = 0
    for case in BLOCK_CASES:
        try:
            await _validator()(case.resume(), {})
        except ValidationFailure:
            blocked += 1
    assert blocked == len(BLOCK_CASES), (
        f"{len(BLOCK_CASES) - blocked} adversarial case(s) slipped through — "
        "this blocks release"
    )
    assert len(BLOCK_CASES) >= 30, "the adversarial set must stay at 30+ blocking cases"


async def test_headings_are_not_required_to_cite() -> None:
    resume = TailoredResume(
        lines=[
            TailoredLine(line_id="h1", section="experience", text="Experience", is_heading=True),
            TailoredLine(
                line_id="l1", section="experience",
                text="Built a retrieval chatbot for customer support",
                source_fact_ids=["f1"],
            ),
        ]
    )
    assert await _validator()(resume, {}) == ValidatorStatus.PASSED.value


async def test_entailment_failure_blocks_a_line_that_passes_every_hard_check() -> None:
    async def always_rejects(*, source: str, rewrite: str) -> bool:
        return False

    resume = TailoredResume(
        lines=[
            TailoredLine(
                line_id="l1", section="experience",
                text="Developed a customer support chatbot",
                source_fact_ids=["f1"],
            )
        ]
    )
    with pytest.raises(ValidationFailure, match="not supported"):
        await _validator(entailment=always_rejects)(resume, {})


async def test_entailment_is_not_consulted_for_already_failing_lines() -> None:
    calls = 0

    async def counting(*, source: str, rewrite: str) -> bool:
        nonlocal calls
        calls += 1
        return True

    resume = TailoredResume(
        lines=[
            TailoredLine(
                line_id="l1", section="experience",
                text="Built a chatbot improving accuracy by 40%",
                source_fact_ids=["f1"],
            )
        ]
    )
    with pytest.raises(ValidationFailure):
        await _validator(entailment=counting)(resume, {})
    assert calls == 0, "no model call should be spent on a line that already hard-failed"
