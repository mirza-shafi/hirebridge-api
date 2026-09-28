from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class StoredFile(Base, UUIDPrimaryKey, Timestamps):
    __tablename__ = "files"

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    mime: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(BigInteger)

    # Doubles as the parse cache key — the same CV uploaded twice is parsed once.
    checksum_sha256: Mapped[str] = mapped_column(String(64), index=True)
    av_scan_status: Mapped[str] = mapped_column(String(16), default="pending")
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_servable(self) -> bool:
        return self.av_scan_status == "clean"
