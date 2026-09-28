"""A figure in one bullet must not license a claim rewritten from another."""

from __future__ import annotations

import pytest

from app.agents.cv_tailor.source_facts import build_source_facts
from app.agents.errors import ValidationFailure
from app.agents.validators.fabrication import FabricationValidator
from app.schemas.enums import ValidatorStatus
from app.schemas.resume import TailoredLine, TailoredResume

ROWS = [
    {
        "id": "f1",
        "kind": "experience",
        "payload": {
            "company": "Autofy Solution",
            "title": "AI Engineer",
            "tech": ["python"],
            "bullets": [
                {"id": "b1", "text": "Built a retrieval chatbot"},
                {"id": "b2", "text": "Cut support response time by 40%"},
            ],
        },
        "start_date": None,
        "end_date": None,
    }
]


def _validator() -> FabricationValidator:
    return FabricationValidator(build_source_facts(ROWS))


def _resume(text: str, facts: list[str]) -> TailoredResume:
    return TailoredResume(
        lines=[TailoredLine(line_id="l1", section="experience", text=text,
                            source_fact_ids=facts)]
    )


async def test_borrowing_a_figure_from_a_sibling_bullet_is_blocked() -> None:
    with pytest.raises(ValidationFailure, match="40"):
        await _validator()(
            _resume("Built a retrieval chatbot that cut response time 40%", ["f1#b1"]), {}
        )


async def test_the_same_figure_passes_when_its_own_bullet_is_cited() -> None:
    status = await _validator()(
        _resume("Cut support response time by 40%", ["f1#b2"]), {}
    )
    assert status == ValidatorStatus.PASSED.value


async def test_citing_the_whole_role_still_resolves() -> None:
    status = await _validator()(_resume("Built a retrieval chatbot", ["f1"]), {})
    assert status == ValidatorStatus.PASSED.value
