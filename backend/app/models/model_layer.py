"""模型层表结构：供应商、模型档案、定价版本、任务路由、调用流水。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, JSONType, utcnow


class ModelProvider(Base):
    __tablename__ = "model_providers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16), default="user")  # system | user
    owner_user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    provider_key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(32), default="openai")  # openai | anthropic
    base_url: Mapped[str] = mapped_column(String(500))
    api_key_enc: Mapped[str | None] = mapped_column(Text)
    key_hint: Mapped[str | None] = mapped_column(String(32))
    allow_private: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    health_status: Mapped[str] = mapped_column(String(16), default="unknown")
    last_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    profiles: Mapped[list[ModelProfile]] = relationship(back_populates="provider")


class ModelProfile(Base):
    __tablename__ = "model_profiles"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_name", name="uq_profile_provider_model"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("model_providers.id", ondelete="CASCADE"))
    model_name: Mapped[str] = mapped_column(String(200))
    display_name: Mapped[str] = mapped_column(String(200))
    context_window: Mapped[int] = mapped_column(Integer)
    max_output: Mapped[int] = mapped_column(Integer)
    supports: Mapped[list[str]] = mapped_column(JSONType, default=list)
    embedding_dim: Mapped[int | None] = mapped_column(Integer)
    capability_tags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    pricing_known: Mapped[bool] = mapped_column(Boolean, default=False)
    pricing_version_id: Mapped[int | None] = mapped_column(BigInteger)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    provider: Mapped[ModelProvider] = relationship(back_populates="profiles")


class PricingVersion(Base):
    __tablename__ = "pricing_versions"
    __table_args__ = (Index("ix_pricing_profile_effective", "model_profile_id", "effective_from"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_profile_id: Mapped[int] = mapped_column(
        ForeignKey("model_profiles.id", ondelete="CASCADE")
    )
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    input_hit: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    input_miss: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    output: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=0)
    time_band: Mapped[str] = mapped_column(String(16), default="all")  # peak | offpeak | all
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModelRoute(Base):
    __tablename__ = "model_routes"
    __table_args__ = (UniqueConstraint("owner_user_id", "task", name="uq_route_owner_task"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), index=True)
    task: Mapped[str] = mapped_column(String(32))
    chain: Mapped[list[dict[str, object]]] = mapped_column(JSONType, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class LLMCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (
        Index("ix_llm_calls_user_time", "user_id", "created_at"),
        Index("ix_llm_calls_model_time", "model_profile_id", "created_at"),
        Index("ix_llm_calls_model_key_time", "model_key", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64))
    task: Mapped[str] = mapped_column(String(32))
    request_id: Mapped[str] = mapped_column(String(64))
    provider_id: Mapped[int | None] = mapped_column(BigInteger)
    model_profile_id: Mapped[int | None] = mapped_column(BigInteger)
    provider_key: Mapped[str | None] = mapped_column(String(64))
    model_key: Mapped[str | None] = mapped_column(String(200))
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_miss_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, default=0)  # 1 元 = 1e6 微元
    first_token_ms: Mapped[int | None] = mapped_column(Integer)
    total_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
