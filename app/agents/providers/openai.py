"""OpenAI Chat Completions adapter using strict json_schema structured output."""

from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.agents.llm import Completion
from app.agents.providers.http import ProviderError, post_json
from app.agents.schema_tools import strictify

SchemaT = TypeVar("SchemaT", bound=BaseModel)

API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIClient:
    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    async def complete(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int
    ) -> Completion:
        data = await post_json(
            self._client,
            API_URL,
            headers=self._headers(),
            payload={
                "model": model,
                "temperature": temperature,
                "max_completion_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120.0,
        )
        content = _first_message(data).get("content") or ""
        return Completion(content=content, model=f"openai:{model}", **_usage(data))

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
                "temperature": temperature,
                "max_completion_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": True,
                        "schema": strictify(schema.model_json_schema()),
                    },
                },
            },
            timeout=180.0,
        )

        message = _first_message(data)
        if message.get("refusal"):
            raise ProviderError(f"OpenAI refused the request: {message['refusal']}")

        content = message.get("content")
        if not content:
            raise ProviderError("OpenAI response contained no content.")

        parsed = schema.model_validate(json.loads(content))
        return parsed, Completion(
            content=parsed.model_dump_json(), model=f"openai:{model}", **_usage(data)
        )


def _first_message(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices") or []
    if not choices:
        raise ProviderError("OpenAI response contained no choices.")
    return choices[0].get("message") or {}


def _usage(data: dict[str, Any]) -> dict[str, int]:
    usage = data.get("usage") or {}
    return {
        "input_tokens": int(usage.get("prompt_tokens", 0)),
        "output_tokens": int(usage.get("completion_tokens", 0)),
    }
