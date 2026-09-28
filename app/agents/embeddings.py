"""Embedding clients.

Note: **Anthropic does not offer an embeddings API.** The embedding provider is therefore
configured separately from `LLM_PROVIDER` — running Claude for generation and OpenAI or
Voyage for embeddings is a normal setup, not a misconfiguration.

Dimension is pinned per model and recorded on every row. Mixing models or dimensions inside
one pgvector index silently produces meaningless similarity scores, so a model change means
a backfill (docs/02-data-model.md §7).
"""

from __future__ import annotations

import hashlib
import logging
import struct
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.agents.providers.http import ProviderError, post_json

log = logging.getLogger("hirebridge.embeddings")

# Known output dimensions. A model absent from here is rejected rather than assumed.
MODEL_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "voyage-3": 1024,
    "voyage-3-lite": 512,
    "voyage-code-3": 1024,
    "fake-embedding": 1536,
}


class UnknownEmbeddingModel(ValueError):
    pass


def dimension_for(model: str) -> int:
    if model not in MODEL_DIMENSIONS:
        raise UnknownEmbeddingModel(
            f"No dimension recorded for embedding model {model!r}. Add it to "
            "MODEL_DIMENSIONS — guessing would corrupt the vector index."
        )
    return MODEL_DIMENSIONS[model]


def content_hash(text: str, model: str) -> str:
    """Cache key. Includes the model, so a model change cannot reuse stale vectors."""
    return hashlib.sha256(f"{model}\x00{text}".encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vector: list[float]
    model: str
    tokens: int


class EmbeddingClient(Protocol):
    async def embed(self, text: str, *, model: str) -> EmbeddingResult: ...
    async def embed_batch(self, texts: list[str], *, model: str) -> list[EmbeddingResult]: ...


class FakeEmbeddingClient:
    """Deterministic vectors derived from the text.

    Same text gives the same vector and different text gives a different one, which is all
    a test needs — and it costs nothing and needs no network.
    """

    async def embed(self, text: str, *, model: str) -> EmbeddingResult:
        dim = dimension_for(model)
        needed = dim * 4

        # Stretch the digest deterministically rather than repeating it, so distant parts of
        # the vector are not identical copies of each other.
        material = bytearray()
        counter = 0
        while len(material) < needed:
            material += hashlib.sha512(f"{counter}\x00{text}".encode()).digest()
            counter += 1

        # Unpacked as unsigned ints, not float32: arbitrary bytes read as floats produce NaN
        # and inf, which would poison the norm.
        ints = struct.unpack(f"<{dim}I", bytes(material[:needed]))
        values = [(i / 0xFFFFFFFF) * 2.0 - 1.0 for i in ints]

        norm = sum(v * v for v in values) ** 0.5 or 1.0
        return EmbeddingResult(
            vector=[v / norm for v in values], model=model, tokens=max(1, len(text) // 4)
        )

    async def embed_batch(self, texts: list[str], *, model: str) -> list[EmbeddingResult]:
        return [await self.embed(t, model=model) for t in texts]


class OpenAIEmbeddingClient:
    URL = "https://api.openai.com/v1/embeddings"

    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient()

    async def embed(self, text: str, *, model: str) -> EmbeddingResult:
        return (await self.embed_batch([text], model=model))[0]

    async def embed_batch(self, texts: list[str], *, model: str) -> list[EmbeddingResult]:
        expected = dimension_for(model)
        data = await post_json(
            self._client,
            self.URL,
            headers={"Authorization": f"Bearer {self._api_key}",
                     "Content-Type": "application/json"},
            payload={"model": model, "input": texts},
            timeout=60.0,
        )
        items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
        if len(items) != len(texts):
            raise ProviderError(
                f"Requested {len(texts)} embeddings, received {len(items)}."
            )
        total = int((data.get("usage") or {}).get("total_tokens", 0))
        return [_result(item["embedding"], model, expected, total // len(items)) for item in items]


class VoyageEmbeddingClient:
    URL = "https://api.voyageai.com/v1/embeddings"

    def __init__(self, api_key: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient()

    async def embed(self, text: str, *, model: str) -> EmbeddingResult:
        return (await self.embed_batch([text], model=model))[0]

    async def embed_batch(self, texts: list[str], *, model: str) -> list[EmbeddingResult]:
        expected = dimension_for(model)
        data = await post_json(
            self._client,
            self.URL,
            headers={"Authorization": f"Bearer {self._api_key}",
                     "Content-Type": "application/json"},
            payload={"model": model, "input": texts},
            timeout=60.0,
        )
        items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
        if len(items) != len(texts):
            raise ProviderError(f"Requested {len(texts)} embeddings, received {len(items)}.")
        total = int((data.get("usage") or {}).get("total_tokens", 0))
        return [_result(item["embedding"], model, expected, total // len(items)) for item in items]


def _result(vector: list[float], model: str, expected_dim: int, tokens: int) -> EmbeddingResult:
    if len(vector) != expected_dim:
        raise ProviderError(
            f"Model {model!r} returned a {len(vector)}-dimension vector, expected "
            f"{expected_dim}. Storing it would corrupt the index."
        )
    return EmbeddingResult(vector=vector, model=model, tokens=tokens)


def get_embedding_client() -> EmbeddingClient:
    from app.core.config import settings

    provider = settings.embedding_provider
    if provider == "fake":
        return FakeEmbeddingClient()
    if not settings.embedding_api_key:
        raise RuntimeError(
            f"EMBEDDING_PROVIDER is {provider!r} but EMBEDDING_API_KEY is not set. "
            "Note that Anthropic has no embeddings API — use OpenAI or Voyage here even "
            "when LLM_PROVIDER is anthropic."
        )
    if provider == "openai":
        return OpenAIEmbeddingClient(settings.embedding_api_key)
    if provider == "voyage":
        return VoyageEmbeddingClient(settings.embedding_api_key)
    raise RuntimeError(f"Unknown EMBEDDING_PROVIDER: {provider!r}")
