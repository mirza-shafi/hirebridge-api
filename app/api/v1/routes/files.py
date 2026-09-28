from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Query, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.api.v1.routes._deps import CurrentUser, Session
from app.core.errors import NotFound, Unprocessable
from app.models import StoredFile
from app.services.storage import (
    MAX_UPLOAD_BYTES,
    LocalStorage,
    UnsupportedUpload,
    detect_mime,
    get_storage,
    storage_key,
)

router = APIRouter(prefix="/files", tags=["files"])


class UploadUrlRequest(BaseModel):
    filename: str = Field(max_length=255)
    content_type: str
    kind: str = "resume_upload"


class UploadUrlResponse(BaseModel):
    file_id: str
    upload_url: str
    fields: dict[str, str]
    max_bytes: int


@router.post("/upload-url", status_code=status.HTTP_201_CREATED)
async def create_upload_url(
    body: UploadUrlRequest, user: CurrentUser, session: Session
) -> UploadUrlResponse:
    """Bytes go straight to storage; they never pass through this process."""
    key = storage_key(user_id=str(user.id), kind=body.kind, filename=body.filename)
    presigned = await get_storage().presign_upload(key, content_type=body.content_type)

    record = StoredFile(
        owner_user_id=user.id, kind=body.kind, storage_key=key,
        mime=body.content_type, size_bytes=0, checksum_sha256="",
        av_scan_status="pending",
    )
    session.add(record)
    await session.flush()

    return UploadUrlResponse(
        file_id=str(record.id),
        upload_url=presigned.url,
        fields=presigned.fields,
        max_bytes=MAX_UPLOAD_BYTES,
    )


@router.post("/local-upload", status_code=status.HTTP_204_NO_CONTENT)
async def local_upload(
    file: UploadFile,
    key: Annotated[str, Query()],
    expires: Annotated[int, Query()],
    signature: Annotated[str, Query()],
    session: Session,
) -> Response:
    """Development-only receiver for `LocalStorage`.

    Deliberately mirrors the real flow — signature verification, magic-byte check, size cap —
    so those paths are exercised locally rather than only in production.
    """
    storage = get_storage()
    if not isinstance(storage, LocalStorage) or not storage.verify(key, expires, signature):
        raise NotFound("Not found.")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise Unprocessable(f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")

    try:
        mime = detect_mime(data[:8], file.content_type or "application/octet-stream")
    except UnsupportedUpload as exc:
        raise Unprocessable(str(exc)) from exc

    await storage.put(key, data, content_type=mime)

    record = await _file_by_key(session, key)
    record.size_bytes = len(data)
    record.mime = mime
    record.checksum_sha256 = hashlib.sha256(data).hexdigest()
    record.av_scan_status = "clean"  # a real scanner hooks in here
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _file_by_key(session: Session, key: str) -> StoredFile:  # type: ignore[valid-type]
    from sqlalchemy import select

    record = (
        await session.execute(select(StoredFile).where(StoredFile.storage_key == key))
    ).scalar_one_or_none()
    if record is None:
        raise NotFound("File record not found.")
    return record
