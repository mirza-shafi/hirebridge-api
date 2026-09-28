"""JSON-schema shaping for provider structured-output modes.

OpenAI's strict json_schema mode requires `additionalProperties: false` and every property
listed in `required` at every level. Pydantic emits neither by default, so the schema is
reshaped here rather than in each adapter.
"""

from __future__ import annotations

from typing import Any


def strictify(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively make a Pydantic JSON schema acceptable to strict structured output."""
    node = dict(schema)

    for key in ("$defs", "definitions"):
        if isinstance(node.get(key), dict):
            node[key] = {name: strictify(sub) for name, sub in node[key].items()}

    if node.get("type") == "object" or "properties" in node:
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["properties"] = {name: strictify(sub) for name, sub in properties.items()}
            # Strict mode has no notion of an optional key; nullable types carry absence.
            node["required"] = list(node["properties"])
        node["additionalProperties"] = False

    if isinstance(items := node.get("items"), dict):
        node["items"] = strictify(items)

    for combinator in ("anyOf", "oneOf", "allOf"):
        if isinstance(node.get(combinator), list):
            node[combinator] = [
                strictify(sub) if isinstance(sub, dict) else sub for sub in node[combinator]
            ]

    return node
