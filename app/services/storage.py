"""Object storage.

File bytes never pass through the API: the client gets a signed URL and uploads straight to
storage. Proxying a 10 MB CV through a worker process to save one round trip is a bad trade
(docs/01-frontend-architecture.md §7).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

log = logging.getLogger("hirebridge.storage")

UPLOAD_TTL = timedelta(minutes=15)
DOWNLOAD_TTL = timedelta(minutes=10)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Checked against the file's magic bytes, not its extension or the client's Content-Type.
MAGIC_SIGNATURES: dict[bytes, str] = {
    b"%PDF-": "application/pdf",
    b"PK\x03\x04": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class UnsupportedUpload(ValueError):
    pass


def detect_mime(head: bytes, declared: str) -> str:
    """Trust the bytes, not the client.

    A DOCX and a ZIP bomb share a magic number, so the declared type still narrows it — but
    a file claiming to be a PDF without `%PDF-` is rejected outright.
    """
    for signature, mime in MAGIC_SIGNATURES.items():
        if head.startswith(signature):
            if mime == declared or (
                signature == b"PK\x03\x04" and declared.endswith("wordprocessingml.document")
            ):
                return mime
            raise UnsupportedUpload(
                f"File content is {mime}, which does not match the declared {declared}."
            )
    if declared == "text/plain":
        return declared
    raise UnsupportedUpload("Upload a PDF, DOCX, or plain text CV.")


def storage_key(*, user_id: str, kind: str, filename: str) -> str:
    """Opaque key. The original filename never appears in the path — CV filenames routinely
    contain the candidate's full name."""
    return f"{kind}/{user_id}/{secrets.token_urlsafe(16)}/{quote(Path(filename).suffix or '.bin')}"


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    url: str
    fields: dict[str, str]
    storage_key: str
    expires_at: datetime
    max_bytes: int = MAX_UPLOAD_BYTES


class Storage(Protocol):
    async def presign_upload(self, key: str, *, content_type: str) -> PresignedUpload: ...
    async def presign_download(self, key: str) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def put(self, key: str, data: bytes, *, content_type: str) -> None: ...


class LocalStorage:
    """Filesystem-backed, for local development and tests.

    Signs URLs with an HMAC so the signing flow is exercised end to end rather than being a
    code path that only runs in production.
    """

    def __init__(self, root: Path, secret: str, base_url: str = "http://localhost:8000") -> None:
        self.root = root
        self.secret = secret.encode()
        self.base_url = base_url.rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _sign(self, key: str, expires: int) -> str:
        return hmac.new(self.secret, f"{key}:{expires}".encode(), hashlib.sha256).hexdigest()

    def verify(self, key: str, expires: int, signature: str) -> bool:
        if datetime.now(UTC).timestamp() > expires:
            return False
        return hmac.compare_digest(self._sign(key, expires), signature)

    async def presign_upload(self, key: str, *, content_type: str) -> PresignedUpload:
        expires_at = datetime.now(UTC) + UPLOAD_TTL
        expires = int(expires_at.timestamp())
        return PresignedUpload(
            url=f"{self.base_url}/v1/files/local-upload",
            fields={
                "key": key,
                "expires": str(expires),
                "signature": self._sign(key, expires),
                "content_type": content_type,
            },
            storage_key=key,
            expires_at=expires_at,
        )

    async def presign_download(self, key: str) -> str:
        expires = int((datetime.now(UTC) + DOWNLOAD_TTL).timestamp())
        return (
            f"{self.base_url}/v1/files/local-download"
            f"?key={quote(key)}&expires={expires}&signature={self._sign(key, expires)}"
        )

    def _path(self, key: str) -> Path:
        # Keys are generated server-side, but a traversal here would be catastrophic.
        resolved = (self.root / key.replace("..", "")).resolve()
        if not str(resolved).startswith(str(self.root.resolve())):
            raise ValueError("Refusing to resolve a key outside the storage root.")
        return resolved

    async def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def get_storage() -> Storage:
    from app.core.config import settings

    if not settings.storage_bucket:
        log.info("No STORAGE_BUCKET configured; using local filesystem storage.")
        return LocalStorage(
            Path(settings.local_storage_path),
            secret=settings.storage_secret_key or "dev-secret",
        )
    raise NotImplementedError(
        "S3-compatible storage is not wired yet — see PROGRESS.md. "
        "LocalStorage covers local development."
    )
