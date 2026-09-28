"""Ollama adapter — a model running on the machine, no API key, no network egress.

Uses Ollama's native `/api/chat` rather than its OpenAI-compatible shim, because `format`
there accepts a full JSON schema and constrains decoding to it. The OpenAI shim only offers
`json_object`, which yields valid JSON of an arbitrary shape — not good enough for agents
whose output is parsed into a Pydantic model.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.agents.embeddings import EmbeddingResult, dimension_for
from app.agents.llm import Completion
from app.agents.providers.http import ProviderError, post_json

SchemaT = TypeVar("SchemaT", bound=BaseModel)

# Local models are slower than hosted ones; a long extraction can genuinely take minutes.
CHAT_TIMEOUT = 600.0
EMBED_TIMEOUT = 120.0


class OllamaClient:
    def __init__(self, base_url: str, *, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient()

    async def complete(
        self, *, prompt: str, model: str, temperature: float, max_tokens: int
    ) -> Completion:
        data = await post_json(
            self._client,
            f"{self.base_url}/api/chat",
            headers={"Content-Type": "application/json"},
            payload={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=CHAT_TIMEOUT,
        )
        return Completion(
            content=(data.get("message") or {}).get("content", ""),
            model=f"ollama:{model}",
            **_usage(data),
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
        data = await post_json(
            self._client,
            f"{self.base_url}/api/chat",
            headers={"Content-Type": "application/json"},
            payload={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                # Constrained decoding against the schema itself.
                "format": schema.model_json_schema(),
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=CHAT_TIMEOUT,
        )

        content = (data.get("message") or {}).get("content")
        if not content:
            raise ProviderError("Ollama returned an empty message.")
        try:
            payload: Any = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                f"Ollama returned content that is not JSON: {content[:200]}"
            ) from exc

        parsed = schema.model_validate(payload)
        return parsed, Completion(
            content=parsed.model_dump_json(), model=f"ollama:{model}", **_usage(data)
        )


class OllamaEmbeddingClient:
    def __init__(self, base_url: str, *, client: httpx.AsyncClient | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient()

    async def embed(self, text: str, *, model: str) -> EmbeddingResult:
        return (await self.embed_batch([text], model=model))[0]

    async def embed_batch(self, texts: list[str], *, model: str) -> list[EmbeddingResult]:
        expected = dimension_for(model)
        data = await post_json(
            self._client,
            f"{self.base_url}/api/embed",
            headers={"Content-Type": "application/json"},
            payload={"model": model, "input": texts},
            timeout=EMBED_TIMEOUT,
        )
        vectors = data.get("embeddings") or []
        if len(vectors) != len(texts):
            raise ProviderError(
                f"Requested {len(texts)} embeddings, received {len(vectors)}."
            )

        results: list[EmbeddingResult] = []
        for vector in vectors:
            if len(vector) != expected:
                raise ProviderError(
                    f"Model {model!r} returned a {len(vector)}-dimension vector, expected "
                    f"{expected}. Check EMBEDDING_DIM matches the model you pulled."
                )
            results.append(EmbeddingResult(vector=vector, model=model, tokens=0))
        return results


def _usage(data: dict[str, Any]) -> dict[str, int]:
    return {
        "input_tokens": int(data.get("prompt_eval_count", 0)),
        "output_tokens": int(data.get("eval_count", 0)),
    }
