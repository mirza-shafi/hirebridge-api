"""Anthropic Messages API adapter.

Structured output is obtained with a forced tool call: the response schema becomes the tool's
input schema, so the model must return an object matching it.
"""

from __future__ import annotations

from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.agents.llm import Completion
from app.agents.providers.http import ProviderError, post_json

SchemaT = TypeVar("SchemaT", bound=BaseModel)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
TOOL_NAME = "emit_result"


class AnthropicClient:
    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient()

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

    async def complete(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int
    ) -> Completion:
        data = await post_json(
            self._client,
            API_URL,
            headers=self._headers(),
            payload={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120.0,
        )
        text = "".join(
            block.get("text", "") for block in data.get("content", [])
            if block.get("type") == "text"
        )
        return Completion(content=text, model=f"anthropic:{model}", **_usage(data))

    async def structured(
        self,
        *,
        prompt: str,
        schema: type[SchemaT],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[SchemaT, Completion]:
        data = await post_json(
            self._client,
            API_URL,
            headers=self._headers(),
            payload={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [
                    {
                        "name": TOOL_NAME,
                        "description": f"Return the result as a {schema.__name__} object.",
                        "input_schema": schema.model_json_schema(),
                    }
                ],
                "tool_choice": {"type": "tool", "name": TOOL_NAME},
            },
            timeout=180.0,
        )

        payload: dict[str, Any] | None = next(
            (
                block.get("input")
                for block in data.get("content", [])
                if block.get("type") == "tool_use" and block.get("name") == TOOL_NAME
            ),
            None,
        )
        if payload is None:
            raise ProviderError("Anthropic response contained no tool_use block.")

        parsed = schema.model_validate(payload)
        return parsed, Completion(
            content=parsed.model_dump_json(), model=f"anthropic:{model}", **_usage(data)
        )


def _usage(data: dict[str, Any]) -> dict[str, int]:
    usage = data.get("usage") or {}
    return {
        "input_tokens": int(usage.get("input_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
    }
