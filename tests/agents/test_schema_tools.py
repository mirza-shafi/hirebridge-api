from __future__ import annotations

from pydantic import BaseModel

from app.agents.schema_tools import strictify


class Inner(BaseModel):
    a: str
    b: int | None = None


class Outer(BaseModel):
    name: str
    optional_note: str | None = None
    items: list[Inner] = []


def test_every_object_level_is_closed_and_fully_required() -> None:
    schema = strictify(Outer.model_json_schema())
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"name", "optional_note", "items"}

    inner = schema["$defs"]["Inner"]
    assert inner["additionalProperties"] is False
    assert set(inner["required"]) == {"a", "b"}


def test_strictify_does_not_mutate_its_input() -> None:
    original = Outer.model_json_schema()
    before = dict(original)
    strictify(original)
    assert original == before
