"""LLM client abstraction.

Provider is swapped in config, never in an agent body (docs/03-agent-specs.md §0).
`FakeLLMClient` is the default in tests — tests never call a provider.
"""

from __future__ import annotations

import json
import logging
import pathlib
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

log = logging.getLogger("hirebridge.llm")

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


# Pricing lives in config/model_pricing.json, not in source: provider prices change, and a
# stale number in code is worse than a visible gap. An unlisted model warns once and costs 0,
# so the hole shows up in the cost dashboard instead of silently under-reporting.
PRICING_PATH = pathlib.Path(__file__).resolve().parents[2] / "config" / "model_pricing.json"

_pricing: dict[str, tuple[float, float]] | None = None
_warned: set[str] = set()


def load_pricing(path: pathlib.Path | None = None) -> dict[str, tuple[float, float]]:
    global _pricing
    if _pricing is not None and path is None:
        return _pricing

    target = path or PRICING_PATH
    table: dict[str, tuple[float, float]] = {}
    try:
        raw = json.loads(target.read_text())
        for model, rates in (raw.get("models") or {}).items():
            table[model] = (float(rates["input"]), float(rates["output"]))
    except FileNotFoundError:
        log.warning("Model pricing file not found at %s; costs will report as 0.", target)
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("Model pricing file at %s is malformed (%s); costs will report as 0.",
                    target, exc)

    if path is None:
        _pricing = table
    return table


def price_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    table = load_pricing()
    rates = table.get(model)
    if rates is None:
        if model not in _warned:
            _warned.add(model)
            log.warning(
                "No price configured for model %r — add it to config/model_pricing.json. "
                "Runs will report $0 until then.",
                model,
            )
        return 0.0
    rate_in, rate_out = rates
    return (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000


def get_llm_client() -> LLMClient:
    """Resolve the configured provider.

    Swapping providers is an environment change, never a code change — the agents only ever
    see this interface (docs/01-architecture.md §5).
    """
    # Imported here so FakeLLMClient stays usable without a populated environment.
    from app.core.config import settings

    if settings.llm_provider == "fake":
        return FakeLLMClient()

    if settings.llm_provider == "ollama":
        # A model on the machine: no key, and nothing leaves the network.
        from app.agents.providers.ollama import OllamaClient

        return OllamaClient(settings.ollama_base_url)

    if not settings.llm_api_key:
        raise RuntimeError(
            f"LLM_PROVIDER is '{settings.llm_provider}' but LLM_API_KEY is not set."
        )

    if settings.llm_provider == "anthropic":
        from app.agents.providers.anthropic import AnthropicClient

        return AnthropicClient(settings.llm_api_key)

    if settings.llm_provider == "openai":
        from app.agents.providers.openai import OpenAIClient

        return OpenAIClient(settings.llm_api_key)

    raise RuntimeError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
