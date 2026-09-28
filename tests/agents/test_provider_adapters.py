"""Provider adapters, exercised against a stub transport — no network, no keys.

What matters here is that both providers produce the same `Completion` shape and map their
failures onto the same exception the runner's retry policy understands.
"""

from __future__ import annotations

import httpx
import pytest
from pydantic import BaseModel

from app.agents.errors import TransientProviderError
from app.agents.providers.anthropic import AnthropicClient
from app.agents.providers.http import ProviderError
from app.agents.providers.openai import OpenAIClient


class Result(BaseModel):
    title: str


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_anthropic_structured_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "content": [
                {"type": "tool_use", "name": "emit_result", "input": {"title": "Backend Engineer"}}
            ],
            "usage": {"input_tokens": 120, "output_tokens": 45},
        })

    parsed, completion = await AnthropicClient("k", client=_client(handler)).structured(
        prompt="p", schema=Result, model="m", temperature=0.0, max_tokens=100
    )
    assert parsed.title == "Backend Engineer"
    assert (completion.input_tokens, completion.output_tokens) == (120, 45)
    assert completion.model == "anthropic:m"


async def test_openai_structured_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"title": "Backend Engineer"}'}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 45},
        })

    parsed, completion = await OpenAIClient("k", client=_client(handler)).structured(
        prompt="p", schema=Result, model="m", temperature=0.0, max_tokens=100
    )
    assert parsed.title == "Backend Engineer"
    assert (completion.input_tokens, completion.output_tokens) == (120, 45)
    assert completion.model == "openai:m"


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_retryable_statuses_raise_the_runners_transient_error(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="upstream busy")

    with pytest.raises(TransientProviderError):
        await AnthropicClient("k", client=_client(handler)).structured(
            prompt="p", schema=Result, model="m", temperature=0.0, max_tokens=10
        )
    with pytest.raises(TransientProviderError):
        await OpenAIClient("k", client=_client(handler)).structured(
            prompt="p", schema=Result, model="m", temperature=0.0, max_tokens=10
        )


async def test_bad_request_is_not_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="invalid model")

    with pytest.raises(ProviderError):
        await OpenAIClient("k", client=_client(handler)).structured(
            prompt="p", schema=Result, model="m", temperature=0.0, max_tokens=10
        )


async def test_timeout_is_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(TransientProviderError):
        await AnthropicClient("k", client=_client(handler)).structured(
            prompt="p", schema=Result, model="m", temperature=0.0, max_tokens=10
        )


async def test_openai_refusal_surfaces_as_a_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "choices": [{"message": {"refusal": "I cannot help with that."}}],
            "usage": {},
        })

    with pytest.raises(ProviderError, match="refused"):
        await OpenAIClient("k", client=_client(handler)).structured(
            prompt="p", schema=Result, model="m", temperature=0.0, max_tokens=10
        )


async def test_anthropic_missing_tool_block_is_an_error_not_a_silent_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": "here you go"}], "usage": {},
        })

    with pytest.raises(ProviderError, match="no tool_use"):
        await AnthropicClient("k", client=_client(handler)).structured(
            prompt="p", schema=Result, model="m", temperature=0.0, max_tokens=10
        )
