"""The runner's contract — these are the rules no individual agent should have to remember."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.agents.base import AgentConfig, AgentRunner
from app.agents.errors import AgentFailed, TransientProviderError, ValidationFailure
from app.agents.llm import Completion, FakeLLMClient
from app.models import AgentRun, RunStatus


class Draft(BaseModel):
    text: str


CONFIG = AgentConfig(
    name="test_agent",
    model="small",
    temperature=0.0,
    max_input_tokens=1000,
    max_output_tokens=500,
    retries=3,
)


class _Session:
    """Minimal stand-in — the runner only flushes and executes."""

    async def flush(self) -> None: ...
    async def execute(self, *_args: object, **_kwargs: object) -> None: ...


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _publish(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("app.services.runs.publish", _publish)
    monkeypatch.setattr("app.agents.base.run_service.publish", _publish)


def _run() -> AgentRun:
    return AgentRun(agent="test_agent", status=RunStatus.QUEUED.value, cost_usd=0)


async def test_records_tokens_on_the_run(fake_llm: FakeLLMClient) -> None:
    fake_llm.queue({"text": "ok"})
    run = _run()
    runner = AgentRunner(_Session(), fake_llm, CONFIG)  # type: ignore[arg-type]

    result = await runner.run(run=run, prompt="hello", schema=Draft)

    assert result.text == "ok"
    assert run.input_tokens == 20
    assert run.output_tokens == 40
    assert run.validator_status == "not_required"


async def test_validation_failure_gets_exactly_one_repair(fake_llm: FakeLLMClient) -> None:
    fake_llm.queue({"text": "bad"})
    fake_llm.queue({"text": "still bad"})
    prompts: list[str] = []
    attempts = 0

    async def always_fails(output: BaseModel, context: dict[str, object]) -> str:
        nonlocal attempts
        attempts += 1
        raise ValidationFailure("line 3 cites no source fact")

    original = fake_llm.structured

    async def spy(**kwargs: object) -> tuple[Draft, Completion]:
        prompts.append(str(kwargs["prompt"]))
        return await original(**kwargs)  # type: ignore[arg-type]

    fake_llm.structured = spy  # type: ignore[method-assign]
    runner = AgentRunner(_Session(), fake_llm, CONFIG)  # type: ignore[arg-type]

    with pytest.raises(AgentFailed) as caught:
        await runner.run(run=_run(), prompt="tailor this", schema=Draft, validator=always_fails)

    assert caught.value.code == "validation_failed"
    assert attempts == 2, "validator should run twice: original + one repair"
    assert "rejected by the output validator" in prompts[1]
    assert "line 3 cites no source fact" in prompts[1]


async def test_oversized_prompt_aborts_on_budget(fake_llm: FakeLLMClient) -> None:
    small = AgentConfig(
        name="test_agent", model="small", temperature=0.0,
        max_input_tokens=5, max_output_tokens=10,
    )
    runner = AgentRunner(_Session(), fake_llm, small)  # type: ignore[arg-type]

    with pytest.raises(AgentFailed) as caught:
        await runner.run(run=_run(), prompt="x" * 4000, schema=Draft)

    assert caught.value.code == "budget_exceeded"


async def test_agent_requiring_a_validator_refuses_to_run_without_one(
    fake_llm: FakeLLMClient,
) -> None:
    guarded = AgentConfig(
        name="cv_tailor", model="large", temperature=0.3,
        max_input_tokens=1000, max_output_tokens=500, requires_validator=True,
    )
    runner = AgentRunner(_Session(), fake_llm, guarded)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="requires_validator"):
        await runner.run(run=_run(), prompt="tailor", schema=Draft)


async def test_transient_errors_retry_then_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    class Flaky(FakeLLMClient):
        async def structured(self, **kwargs: object):  # type: ignore[override]
            nonlocal calls
            calls += 1
            raise TransientProviderError("502 from provider")

    monkeypatch.setattr("asyncio.sleep", lambda _s: _noop())
    runner = AgentRunner(_Session(), Flaky(), CONFIG)  # type: ignore[arg-type]

    with pytest.raises(AgentFailed) as caught:
        await runner.run(run=_run(), prompt="hello", schema=Draft)

    assert caught.value.code == "provider_unavailable"
    assert calls == 3


async def _noop() -> None:
    return None
