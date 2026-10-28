"""会话与消息表。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import new_ulid
from app.models.base import Base, utcnow


class ChatSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_companion", "user_id", "companion_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    companion_id: Mapped[int] = mapped_column(ForeignKey("companions.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(60), default="")
    state: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ulid: Mapped[str] = mapped_column(String(26), unique=True)
    origin_device_id: Mapped[str | None] = mapped_column(String(64), default="local")


class ChatMessage(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_messages_session_seq"),
        Index("ix_messages_session_seq", "session_id", "seq"),
        Index("ix_messages_client_request", "client_request_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    client_request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ulid: Mapped[str] = mapped_column(String(26), unique=True)
    origin_device_id: Mapped[str | None] = mapped_column(String(64), default="local")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionSummary(Base):
    __tablename__ = "conversation_summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ulid: Mapped[str] = mapped_column(String(26), default=new_ulid)
    origin_device_id: Mapped[str | None] = mapped_column(String(64))
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[str] = mapped_column(Text)
    covered_seq: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
