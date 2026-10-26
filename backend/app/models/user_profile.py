"""用户身份：账号级通用身份 + 伴侣级覆盖身份。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class UserProfile(Base):
    """账号级“我是谁”，所有伴侣默认都知道。"""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True)
    nickname: Mapped[str] = mapped_column(String(20), default="")
    identity: Mapped[str] = mapped_column(String(60), default="")
    age: Mapped[int | None] = mapped_column()
    gender: Mapped[str] = mapped_column(String(8), default="")
    city: Mapped[str] = mapped_column(String(40), default="")
    background: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class CompanionUserProfile(Base):
    """与某个伴侣对话时的“我是谁”，字段为空表示沿用通用身份。"""

    __tablename__ = "companion_user_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "companion_id", name="uq_companion_user_profile"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64))
    companion_id: Mapped[int] = mapped_column(ForeignKey("companions.id", ondelete="CASCADE"))
    nickname: Mapped[str | None] = mapped_column(String(20))
    identity: Mapped[str | None] = mapped_column(String(60))
    age: Mapped[int | None] = mapped_column()
    gender: Mapped[str | None] = mapped_column(String(8))
    city: Mapped[str | None] = mapped_column(String(40))
    background: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
