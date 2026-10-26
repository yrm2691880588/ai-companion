"""自定义模型表。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class CustomModelRow(Base):
    __tablename__ = "custom_models"
    __table_args__ = (UniqueConstraint("provider_key", "model_name", name="uq_custom_model"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_key: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200))
    context_window: Mapped[int] = mapped_column(Integer, default=32768)
    max_output: Mapped[int] = mapped_column(Integer, default=8192)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
