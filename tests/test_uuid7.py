from __future__ import annotations

from app.db.base import uuid7


def test_uuid7_version_and_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert (value.bytes[8] & 0xC0) == 0x80


def test_uuid7_is_time_ordered() -> None:
    values = [uuid7() for _ in range(50)]
    assert values == sorted(values, key=lambda u: u.bytes[:6])
