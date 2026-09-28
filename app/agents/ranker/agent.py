"""Ranking Justification agent.

Generated lazily — the top N plus anyone the recruiter opens. Writing 400 justifications up
front wastes roughly 90% of the spend, since most are never read.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from app.agents.base import AgentConfig, AgentRunner
from app.agents.llm import LLMClient
from app.agents.ranker.prompts import v1
from app.agents.ranker.rendering import render_comparison, render_scores
from app.schemas.ranking import Justification
from app.services.ranking import ScoreResult
from app.services.scoring_payload import assert_allowlisted

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import AgentRun

__all__ = [
    "DEFAULT_JUSTIFY_TOP_N",
    "RankerJustifierAgent",
    "config",
    "render_comparison",
    "render_scores",
]

AGENT_NAME = "ranker_justifier"
DEFAULT_JUSTIFY_TOP_N = 25


def config(model: str) -> AgentConfig:
    return AgentConfig(
        name=AGENT_NAME,
        model=model,
        temperature=0.0,      # an explanation of fixed arithmetic should not vary
        max_input_tokens=8_000,
        max_output_tokens=2_000,
        prompt_version=v1.VERSION,
        timeout_seconds=60,
    )


class RankerJustifierAgent:
    def __init__(self, session: AsyncSession, llm: LLMClient, model: str) -> None:
        self.runner = AgentRunner(session, llm, config(model))

    async def justify(
        self,
        *,
        run: AgentRun,
        job_text: str,
        candidate_payload: dict[str, Any],
        result: ScoreResult,
        neighbour: ScoreResult | None = None,
    ) -> Justification:
        # Belt and braces: the payload builder already enforces this, but this agent is the
        # one place a protected attribute could reach a model and influence a hiring
        # decision, so it is checked again at the call site.
        assert_allowlisted(candidate_payload)

        return await self.runner.run(
            run=run,
            prompt=v1.build(
                job=job_text,
                candidate=json.dumps(candidate_payload, indent=2, default=str),
                scores=render_scores(result),
                comparison=render_comparison(result, neighbour),
            ),
            schema=Justification,
        )
