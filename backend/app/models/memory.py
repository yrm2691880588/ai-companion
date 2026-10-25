"""长期记忆表。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_user_companion_status", "user_id", "companion_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64))
    companion_id: Mapped[int] = mapped_column(ForeignKey("companions.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), default=0.7)
    status: Mapped[str] = mapped_column(String(16), default="active")
    source_session_id: Mapped[int | None] = mapped_column(BigInteger)
    source_message_id: Mapped[int | None] = mapped_column(BigInteger)
    quote: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
