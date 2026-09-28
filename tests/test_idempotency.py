from __future__ import annotations

from app.services.idempotency import scoped_key


def test_keys_are_namespaced_per_user_and_agent() -> None:
    a = scoped_key("user_a", "cv_tailor", "abc123")
    b = scoped_key("user_b", "cv_tailor", "abc123")
    c = scoped_key("user_a", "question_gen", "abc123")
    assert len({a, b, c}) == 3, "two users reusing a key must not collide"
