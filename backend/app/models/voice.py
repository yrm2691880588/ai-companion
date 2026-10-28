"""语音功能表结构。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, utcnow


class VoiceProviderSettingRow(Base):
    __tablename__ = "voice_provider_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_key: Mapped[str] = mapped_column(String(64), unique=True)
    credentials_enc: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class VoiceVoiceRow(Base):
    __tablename__ = "voice_voices"
    __table_args__ = (UniqueConstraint("provider_key", "voice_id", name="uq_voice_provider_voice"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_key: Mapped[str] = mapped_column(String(64))
    voice_id: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(128))
    gender: Mapped[str] = mapped_column(String(16), default="")
    tags: Mapped[list[str] | None] = mapped_column(JSONType)
    params_schema: Mapped[dict[str, object] | None] = mapped_column(JSONType)
    cached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VoiceUsageRow(Base):
    __tablename__ = "voice_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[int | None] = mapped_column(BigInteger)
    provider_key: Mapped[str] = mapped_column(String(64))
    asr_ms: Mapped[int | None] = mapped_column(Integer)
    tts_chars: Mapped[int | None] = mapped_column(Integer)
    cost_cny: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    status: Mapped[str] = mapped_column(String(16), default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
