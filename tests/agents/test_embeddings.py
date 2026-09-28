from __future__ import annotations

import httpx
import pytest

from app.agents.embeddings import (
    FakeEmbeddingClient,
    OpenAIEmbeddingClient,
    UnknownEmbeddingModel,
    content_hash,
    dimension_for,
)
from app.agents.providers.http import ProviderError
from app.services.embedding_text import job_embedding_text, profile_embedding_text

FACT_ROWS = [
    {
        "kind": "experience",
        "payload": {
            "title": "AI Engineer", "company": "Autofy Solution",
            "tech": ["python", "fastapi"],
            "bullets": [{"id": "b1", "text": "Built a retrieval chatbot"}],
        },
    },
    {"kind": "education", "payload": {"degree": "B.Sc.", "field": "Computer Science"}},
]


def test_unknown_model_is_rejected_rather_than_assumed() -> None:
    with pytest.raises(UnknownEmbeddingModel):
        dimension_for("some-new-model")


def test_content_hash_includes_the_model() -> None:
    """A model change must invalidate the cache; reusing vectors across models is silent
    corruption of the similarity scores."""
    assert content_hash("hello", "a") != content_hash("hello", "b")
    assert content_hash("hello", "a") == content_hash("hello", "a")


async def test_fake_client_is_deterministic_and_normalised() -> None:
    client = FakeEmbeddingClient()
    first = await client.embed("hello", model="fake-embedding")
    second = await client.embed("hello", model="fake-embedding")
    other = await client.embed("different", model="fake-embedding")

    assert first.vector == second.vector
    assert first.vector != other.vector
    assert len(first.vector) == 1536
    assert abs(sum(v * v for v in first.vector) ** 0.5 - 1.0) < 1e-5
    assert all(-1.0 <= v <= 1.0 for v in first.vector)
    assert all(v == v for v in first.vector), "no NaN"
    assert len(set(first.vector)) > 1000, "the vector must not be a repeated block"


@pytest.mark.parametrize("model", ["text-embedding-3-large", "voyage-3", "voyage-3-lite"])
async def test_fake_client_honours_each_model_dimension(model: str) -> None:
    result = await FakeEmbeddingClient().embed("hello", model=model)
    assert len(result.vector) == dimension_for(model)


async def test_wrong_dimension_from_a_provider_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": [{"index": 0, "embedding": [0.1] * 999}],
            "usage": {"total_tokens": 5},
        })

    client = OpenAIEmbeddingClient("k", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderError, match="corrupt the index"):
        await client.embed("hello", model="text-embedding-3-small")


async def test_batch_order_is_preserved() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": [
                {"index": 1, "embedding": [0.2] * 1536},
                {"index": 0, "embedding": [0.1] * 1536},
            ],
            "usage": {"total_tokens": 10},
        })

    client = OpenAIEmbeddingClient("k", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    results = await client.embed_batch(["a", "b"], model="text-embedding-3-small")
    assert results[0].vector[0] == pytest.approx(0.1)
    assert results[1].vector[0] == pytest.approx(0.2)


def test_profile_text_keeps_signal_and_drops_identity() -> None:
    text = profile_embedding_text(
        headline="Backend Developer", summary=None, fact_rows=FACT_ROWS
    )
    assert "AI Engineer at Autofy Solution" in text
    assert "Built a retrieval chatbot" in text
    assert "Skills: fastapi, python" in text


def test_job_text_excludes_boilerplate() -> None:
    text = job_embedding_text(
        title="Backend Engineer",
        seniority="mid",
        structured={
            "responsibilities": ["Build APIs"],
            "requirements": [{"text": "3 years Python"}],
            "benefits": ["Competitive salary", "Dynamic team"],
        },
        must_have=["python"],
        nice_to_have=["postgres"],
    )
    assert "Build APIs" in text
    assert "3 years Python" in text
    assert "Competitive salary" not in text, "boilerplate only adds noise to similarity"
    assert "Dynamic team" not in text
