"""Resume Parser agent — CV text to structured, citable profile facts."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentConfig, AgentRunner
from app.agents.llm import LLMClient
from app.agents.resume_parser.mapping import (
    LOW_CONFIDENCE,
    completeness_score,
    needs_review,
    to_fact_rows,
)
from app.agents.resume_parser.prompts import v1
from app.models import AgentRun
from app.schemas.profile import ParsedProfile

__all__ = [
    "LOW_CONFIDENCE",
    "ResumeParserAgent",
    "completeness_score",
    "config",
    "needs_review",
    "to_fact_rows",
]

AGENT_NAME = "resume_parser"


def config(model: str) -> AgentConfig:
    return AgentConfig(
        name=AGENT_NAME,
        model=model,
        temperature=0.0,
        max_input_tokens=20_000,
        max_output_tokens=8_000,
        prompt_version=v1.VERSION,
        timeout_seconds=120,
    )


class ResumeParserAgent:
    def __init__(self, session: AsyncSession, llm: LLMClient, model: str) -> None:
        self.runner = AgentRunner(session, llm, config(model))

    async def parse(self, *, run: AgentRun, text: str) -> ParsedProfile:
        return await self.runner.run(run=run, prompt=v1.build(text), schema=ParsedProfile)
