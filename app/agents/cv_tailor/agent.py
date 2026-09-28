"""CV Tailoring agent — the highest-risk agent in the product.

Declared `requires_validator=True`, so the runner refuses to execute it without a validator
attached. That is the mechanical enforcement of product rule 1: this agent cannot run
ungrounded, even by mistake.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.agents.base import AgentConfig, AgentRunner
from app.agents.cv_tailor.prompts import v1
from app.agents.cv_tailor.source_facts import build_source_facts, render_for_prompt
from app.agents.llm import LLMClient
from app.agents.validators.fabrication import EntailmentChecker, FabricationValidator
from app.schemas.resume import SourceFact, TailoredResume

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models import AgentRun

AGENT_NAME = "cv_tailor"


def config(model: str) -> AgentConfig:
    return AgentConfig(
        name=AGENT_NAME,
        model=model,
        temperature=0.3,       # some phrasing variety; not so much that it drifts
        max_input_tokens=24_000,
        max_output_tokens=8_000,
        prompt_version=v1.VERSION,
        timeout_seconds=180,
        requires_validator=True,
    )


class CVTailorAgent:
    def __init__(self, session: AsyncSession, llm: LLMClient, model: str) -> None:
        self.runner = AgentRunner(session, llm, config(model))

    async def tailor(
        self,
        *,
        run: AgentRun,
        fact_rows: list[dict[str, Any]],
        job_text: str,
        entailment: EntailmentChecker | None = None,
    ) -> tuple[TailoredResume, dict[str, Any]]:
        """Returns the tailored CV and the validator's context (findings, status).

        Raises `AgentFailed` when validation fails after its one repair attempt — no PDF is
        rendered and nothing reaches the candidate.
        """
        facts: list[SourceFact] = build_source_facts(fact_rows)
        validator = FabricationValidator(facts, entailment=entailment)
        context: dict[str, Any] = {}

        result = await self.runner.run(
            run=run,
            prompt=v1.build(facts=render_for_prompt(facts), job=job_text),
            schema=TailoredResume,
            validator=validator,
            context=context,
        )
        return result, context
