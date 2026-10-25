"""演练场景与运行记录表、安全事件表。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, utcnow


class RoleplayScenario(Base):
    __tablename__ = "roleplay_scenarios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(60))
    category: Mapped[str] = mapped_column(String(32))
    role: Mapped[str] = mapped_column(String(60))
    goal: Mapped[str] = mapped_column(String(200))
    difficulty: Mapped[int] = mapped_column(Integer, default=2)
    max_turns: Mapped[int] = mapped_column(Integer, default=8)
    opening: Mapped[str] = mapped_column(Text)
    tips: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class RoleplayRun(Base):
    __tablename__ = "roleplay_runs"
    __table_args__ = (Index("ix_roleplay_runs_user", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64))
    companion_id: Mapped[int] = mapped_column(ForeignKey("companions.id", ondelete="CASCADE"))
    scenario_key: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="active")
    max_turns: Mapped[int] = mapped_column(Integer, default=8)
    turns_played: Mapped[int] = mapped_column(Integer, default=0)
    review: Mapped[dict[str, object] | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SafetyEvent(Base):
    __tablename__ = "safety_events"
    __table_args__ = (Index("ix_safety_events_user", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64))
    session_id: Mapped[int | None] = mapped_column(BigInteger)
    level: Mapped[str] = mapped_column(String(16))
    keywords: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
