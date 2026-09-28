"""LLM client abstraction.

Provider is swapped in config, never in an agent body (docs/03-agent-specs.md §0).
`FakeLLMClient` is the default in tests — tests never call a provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

from app.core.config import settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class Completion:
    content: str
    input_tokens: int
    output_tokens: int
    model: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMClient(Protocol):
    async def complete(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int
    ) -> Completion: ...

    async def structured(
        self,
        *,
        prompt: str,
        schema: type[SchemaT],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[SchemaT, Completion]: ...


class FakeLLMClient:
    """Deterministic stand-in. Register fixtures with `queue()`."""

    def __init__(self) -> None:
        self._queued: list[Any] = []

    def queue(self, value: Any) -> None:
        self._queued.append(value)

    async def complete(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int
    ) -> Completion:
        content = self._queued.pop(0) if self._queued else "fake-response"
        return Completion(
            content=str(content), input_tokens=10, output_tokens=5, model=f"fake:{model}"
        )

    async def structured(
        self,
        *,
        prompt: str,
        schema: type[SchemaT],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[SchemaT, Completion]:
        if not self._queued:
            raise AssertionError(
                f"FakeLLMClient has no queued fixture for {schema.__name__}; "
                "call client.queue(instance) in the test."
            )
        value = self._queued.pop(0)
        parsed = value if isinstance(value, schema) else schema.model_validate(value)
        return parsed, Completion(
            content=parsed.model_dump_json(), input_tokens=20, output_tokens=40, model=f"fake:{model}"
        )


# USD per 1M tokens, (input, output). Fill in when the provider is chosen —
# an unlisted model costs 0, which makes the gap visible in the cost dashboard
# rather than silently under-reporting.
PRICING: dict[str, tuple[float, float]] = {}


def price_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rate_in, rate_out = PRICING.get(model, (0.0, 0.0))
    return (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000


def get_llm_client() -> LLMClient:
    if settings.llm_provider == "fake":
        return FakeLLMClient()
    raise NotImplementedError(
        f"Provider '{settings.llm_provider}' is not wired yet. "
        "See PROGRESS.md → Blocked / needs a decision."
    )
