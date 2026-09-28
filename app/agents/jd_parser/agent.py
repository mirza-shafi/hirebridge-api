"""JD Parser agent — raw job description to a structured job record."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentConfig, AgentRunner
from app.agents.jd_parser.mapping import slugify, to_job_fields
from app.agents.jd_parser.prompts import v1
from app.agents.llm import LLMClient
from app.models import AgentRun
from app.schemas.job import StructuredJD

__all__ = ["JDParserAgent", "config", "slugify", "to_job_fields"]

AGENT_NAME = "jd_parser"


def config(model: str) -> AgentConfig:
    return AgentConfig(
        name=AGENT_NAME,
        model=model,
        temperature=0.0,          # extraction, not generation
        max_input_tokens=12_000,
        max_output_tokens=4_000,
        prompt_version=v1.VERSION,
        timeout_seconds=90,
    )


class JDParserAgent:
    def __init__(self, session: AsyncSession, llm: LLMClient, model: str) -> None:
        self.runner = AgentRunner(session, llm, config(model))

    async def parse(self, *, run: AgentRun, description: str) -> StructuredJD:
        return await self.runner.run(
            run=run,
            prompt=v1.build(description),
            schema=StructuredJD,
        )
