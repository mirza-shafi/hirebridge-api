from __future__ import annotations

import base64
import hashlib
import hmac
import time

import pytest

from app.api.v1.routes.webhooks import _verify
from app.core.errors import Forbidden

SECRET_BYTES = b"0123456789abcdef0123456789abcdef"
SECRET = "whsec_" + base64.b64encode(SECRET_BYTES).decode()


def _sign(body: bytes, svix_id: str, ts: str) -> str:
    signed = f"{svix_id}.{ts}.".encode() + body
    return "v1," + base64.b64encode(hmac.new(SECRET_BYTES, signed, hashlib.sha256).digest()).decode()


@pytest.fixture(autouse=True)
def _secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.v1.routes.webhooks.settings.clerk_webhook_secret", SECRET)


def test_valid_signature_passes() -> None:
    body, svix_id, ts = b'{"type":"user.created"}', "msg_1", str(int(time.time()))
    _verify(body, svix_id, ts, _sign(body, svix_id, ts))


def test_tampered_body_is_rejected() -> None:
    body, svix_id, ts = b'{"type":"user.created"}', "msg_1", str(int(time.time()))
    signature = _sign(body, svix_id, ts)
    with pytest.raises(Forbidden):
        _verify(b'{"type":"user.deleted"}', svix_id, ts, signature)


def test_replayed_old_timestamp_is_rejected() -> None:
    body, svix_id = b"{}", "msg_1"
    old = str(int(time.time()) - 3600)
    with pytest.raises(Forbidden, match="tolerance"):
        _verify(body, svix_id, old, _sign(body, svix_id, old))
