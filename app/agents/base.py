"""The agent execution model.

One place implements the rules from docs/03-agent-specs.md §0, so no individual agent has to
remember them:

  * every model call is recorded on its AgentRun (audit log, cost ledger, eval dataset);
  * 3 attempts on transient provider errors, exponential backoff;
  * a *validation* failure is not retried blindly — one repair attempt with the validator's
    complaint appended, then a hard failure. Silent degradation is worse than an error;
  * per-run and per-org token ceilings abort rather than overspend;
  * model and temperature come from config, never from the agent body.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.errors import AgentFailed, TransientProviderError, ValidationFailure
from app.agents.llm import Completion, LLMClient, price_usd
from app.core.logging import run_id_var
from app.models import AgentRun, RunStatus
from app.services import budget as budget_service
from app.services import runs as run_service

log = logging.getLogger("hirebridge.agent")

SchemaT = TypeVar("SchemaT", bound=BaseModel)

__all__ = [
    "AgentConfig",
    "AgentFailed",
    "AgentRunner",
    "TransientProviderError",
    "ValidationFailure",
    "Validator",
]

REPAIR_PREAMBLE = (
    "Your previous response was rejected by the output validator.\n"
    "Complaint: {complaint}\n"
    "Produce a corrected response. Do not introduce any information that is not present "
    "in the source material.\n\n"
)


class Validator(Protocol):
    """Deterministic post-pass. Raises ValidationFailure; returns a status string on success."""

    async def __call__(self, output: BaseModel, context: dict[str, Any]) -> str: ...


@dataclass(frozen=True, slots=True)
class AgentConfig:
    name: str
    model: str
    temperature: float
    max_input_tokens: int
    max_output_tokens: int
    prompt_version: str = "v1"
    timeout_seconds: int = 120
    retries: int = 3
    requires_validator: bool = False


class AgentRunner:
    """Executes one agent against one AgentRun row."""

    def __init__(self, session: AsyncSession, llm: LLMClient, config: AgentConfig) -> None:
        self.session = session
        self.llm = llm
        self.config = config

    async def run(
        self,
        *,
        run: AgentRun,
        prompt: str,
        schema: type[SchemaT],
        validator: Validator | None = None,
        context: dict[str, Any] | None = None,
    ) -> SchemaT:
        if self.config.requires_validator and validator is None:
            # docs/03-agent-specs.md §3: the tailoring agent ships with its validator, never without.
            raise RuntimeError(
                f"Agent '{self.config.name}' declares requires_validator "
                "but no validator was supplied."
            )

        token = run_id_var.set(str(run.id))
        try:
            return await self._execute(run, prompt, schema, validator, context or {})
        finally:
            run_id_var.reset(token)

    async def _execute(
        self,
        run: AgentRun,
        prompt: str,
        schema: type[SchemaT],
        validator: Validator | None,
        context: dict[str, Any],
    ) -> SchemaT:
        run.agent = self.config.name
        run.prompt_version = self.config.prompt_version
        run.model = self.config.model
        run.status = RunStatus.RUNNING.value

        await budget_service.assert_org_within_budget(self.session, run.org_id)

        estimated = budget_service.estimate_tokens(prompt)
        if estimated > self.config.max_input_tokens:
            await self._abort_budget(
                run,
                f"Prompt is approximately {estimated} tokens, over the "
                f"{self.config.max_input_tokens} limit for this agent.",
            )

        current_prompt = prompt
        repair_used = False
        started = time.perf_counter()

        for attempt in range(1, self.config.retries + 1):
            run.attempt = attempt
            try:
                parsed, completion = await asyncio.wait_for(
                    self.llm.structured(
                        prompt=current_prompt,
                        schema=schema,
                        model=self.config.model,
                        temperature=self.config.temperature,
                        max_tokens=self.config.max_output_tokens,
                    ),
                    timeout=self.config.timeout_seconds,
                )
            except (TransientProviderError, TimeoutError, asyncio.TimeoutError) as exc:
                if attempt >= self.config.retries:
                    await self._fail(run, "provider_unavailable", str(exc), started)
                backoff = 2 ** (attempt - 1)
                log.warning(
                    "agent %s transient failure on attempt %d, retrying in %ds",
                    self.config.name,
                    attempt,
                    backoff,
                )
                await asyncio.sleep(backoff)
                continue
            except ValidationError as exc:
                # The model returned something that does not fit the schema at all.
                if attempt >= self.config.retries:
                    await self._fail(run, "schema_mismatch", str(exc), started)
                continue

            await self._record_usage(run, completion)

            if validator is None:
                run.validator_status = "not_required"
                await self._succeed(run, started)
                return parsed

            try:
                run.validator_status = await validator(parsed, context)
            except ValidationFailure as failure:
                if repair_used:
                    # One repair attempt, then stop. Never ship unverified output.
                    run.validator_status = failure.status
                    await self._fail(run, "validation_failed", failure.complaint, started)
                repair_used = True
                current_prompt = REPAIR_PREAMBLE.format(complaint=failure.complaint) + prompt
                log.warning(
                    "agent %s validation failed, attempting one repair: %s",
                    self.config.name,
                    failure.complaint,
                )
                continue

            await self._succeed(run, started)
            return parsed

        await self._fail(run, "retries_exhausted", "The agent did not produce valid output.", started)
        raise AssertionError("unreachable")  # pragma: no cover

    async def _record_usage(self, run: AgentRun, completion: Completion) -> None:
        # Column defaults are applied on flush, not on construction, so a run that has not
        # been flushed yet has None in these fields. Accumulating defensively keeps the
        # runner correct regardless of when the caller flushed.
        run.input_tokens = (run.input_tokens or 0) + completion.input_tokens
        run.output_tokens = (run.output_tokens or 0) + completion.output_tokens
        run.provider = completion.model.split(":", 1)[0]
        run.cost_usd = float(run.cost_usd or 0) + price_usd(
            self.config.model, completion.input_tokens, completion.output_tokens
        )
        await budget_service.record_org_usage(self.session, run.org_id, completion.total_tokens)

    async def _succeed(self, run: AgentRun, started: float) -> None:
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        await run_service.mark_succeeded(self.session, run, output_ref={"agent": self.config.name})

    async def _fail(self, run: AgentRun, code: str, message: str, started: float) -> None:
        run.latency_ms = int((time.perf_counter() - started) * 1000)
        await run_service.mark_failed(self.session, run, code=code, message=message)
        raise AgentFailed(code, message)

    async def _abort_budget(self, run: AgentRun, message: str) -> None:
        run.status = RunStatus.ABORTED_BUDGET.value
        run.error_code = "budget_exceeded"
        run.error_message = message
        await self.session.flush()
        await run_service.publish(run.id, "aborted_budget", {"message": message})
        raise AgentFailed("budget_exceeded", message)
