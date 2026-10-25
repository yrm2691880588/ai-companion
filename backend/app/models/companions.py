"""伴侣与人设版本的表结构。"""

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, utcnow


class Companion(Base):
    __tablename__ = "companions"
    __table_args__ = (Index("ix_companions_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(16), default="active")
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    memory_enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    personas: Mapped[list[CompanionPersona]] = relationship(
        back_populates="companion", cascade="all, delete-orphan"
    )


class CompanionPersona(Base):
    __tablename__ = "companion_personas"
    __table_args__ = (
        UniqueConstraint("companion_id", "version", name="uq_persona_companion_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    companion_id: Mapped[int] = mapped_column(ForeignKey("companions.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    persona: Mapped[dict[str, object]] = mapped_column(JSONType)
    compiled_prompt: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    companion: Mapped[Companion] = relationship(back_populates="personas")


class CompanionTemplate(Base):
    __tablename__ = "companion_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    category: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(40))
    tagline: Mapped[str] = mapped_column(String(120))
    persona: Mapped[dict[str, object]] = mapped_column(JSONType)
    enabled: Mapped[bool] = mapped_column(default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
