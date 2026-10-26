"""同步 outbox 表（只写不读，为将来同步预留）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, utcnow


class SyncOutbox(Base):
    __tablename__ = "sync_outbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_ulid: Mapped[str] = mapped_column(String(26))
    operation: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict[str, object] | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
