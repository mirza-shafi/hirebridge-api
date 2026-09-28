from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.agents.llm import FakeLLMClient


class Sample(BaseModel):
    title: str


async def test_structured_uses_queued_fixture(fake_llm: FakeLLMClient) -> None:
    fake_llm.queue({"title": "Backend Engineer"})
    parsed, completion = await fake_llm.structured(
        prompt="x", schema=Sample, model="small", temperature=0, max_tokens=100
    )
    assert parsed.title == "Backend Engineer"
    assert completion.total_tokens == 60


async def test_structured_without_fixture_fails_loudly(fake_llm: FakeLLMClient) -> None:
    with pytest.raises(AssertionError, match="no queued fixture"):
        await fake_llm.structured(
            prompt="x", schema=Sample, model="small", temperature=0, max_tokens=100
        )
