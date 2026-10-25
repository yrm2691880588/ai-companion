"""llm_calls 落库与按模型汇总（SQL 实现）。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.usage import (
    CallRecord,
    DailyUsage,
    ModelUsage,
    UsageSummary,
    UsageTotals,
)
from app.models.model_layer import LLMCall


class SqlUsageRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, record: CallRecord) -> None:
        async with self._session_factory() as session:
            session.add(
                LLMCall(
                    user_id=record.user_id,
                    task=record.task,
                    request_id=record.request_id,
                    provider_id=None,
                    model_profile_id=None,
                    provider_key=record.provider_key,
                    model_key=record.model_key,
                    attempt_no=record.attempt_no,
                    prompt_tokens=record.prompt_tokens,
                    completion_tokens=record.completion_tokens,
                    cache_hit_tokens=record.cache_hit_tokens,
                    cache_miss_tokens=record.cache_miss_tokens,
                    cost_micros=record.cost_micros,
                    first_token_ms=record.first_token_ms,
                    total_ms=record.total_ms,
                    status=record.status,
                    error_code=record.error_code,
                )
            )
            await session.commit()

    async def summary(self, user_id: str, *, days: int) -> UsageSummary:
        if days < 1 or days > 90:
            raise ValueError("统计天数必须在 1–90 之间")
        since = datetime.now(UTC) - timedelta(days=days)
        async with self._session_factory() as session:
            model_rows = (
                await session.execute(
                    select(
                        LLMCall.model_key,
                        func.count().label("calls"),
                        func.count().filter(LLMCall.status == "ok").label("ok_calls"),
                        func.coalesce(func.sum(LLMCall.prompt_tokens), 0).label("prompt_tokens"),
                        func.coalesce(func.sum(LLMCall.completion_tokens), 0).label(
                            "output_tokens"
                        ),
                        func.coalesce(func.sum(LLMCall.cache_hit_tokens), 0).label("hit"),
                        func.coalesce(func.sum(LLMCall.cache_miss_tokens), 0).label("miss"),
                        func.coalesce(func.sum(LLMCall.cost_micros), 0).label("cost"),
                        func.avg(LLMCall.first_token_ms).label("avg_first_token"),
                    )
                    .where(LLMCall.user_id == user_id, LLMCall.created_at >= since)
                    .group_by(LLMCall.model_key)
                    .order_by(func.count().desc())
                )
            ).all()
            day_rows = (
                await session.execute(
                    select(
                        func.date_trunc("day", LLMCall.created_at).label("day"),
                        func.count().label("calls"),
                        func.coalesce(func.sum(LLMCall.cost_micros), 0).label("cost"),
                    )
                    .where(LLMCall.user_id == user_id, LLMCall.created_at >= since)
                    .group_by("day")
                    .order_by("day")
                )
            ).all()

        summary = UsageSummary(days=days)
        for row in model_rows:
            totals = UsageTotals(
                calls=int(row.calls),
                ok_calls=int(row.ok_calls),
                input_tokens=int(row.prompt_tokens),
                output_tokens=int(row.output_tokens),
                cache_hit_tokens=int(row.hit),
                cache_miss_tokens=int(row.miss),
                cost_micros=int(row.cost),
            )
            summary.by_model.append(
                ModelUsage(
                    model_key=row.model_key or "unknown",
                    totals=totals,
                    avg_first_token_ms=float(row.avg_first_token) if row.avg_first_token else None,
                )
            )
            for field_name in (
                "calls",
                "ok_calls",
                "input_tokens",
                "output_tokens",
                "cache_hit_tokens",
                "cache_miss_tokens",
                "cost_micros",
            ):
                setattr(
                    summary.totals,
                    field_name,
                    getattr(summary.totals, field_name) + getattr(totals, field_name),
                )
        for row in day_rows:
            day = row.day.date() if isinstance(row.day, datetime) else row.day
            summary.daily.append(
                DailyUsage(day=_as_date(day), calls=int(row.calls), cost_micros=int(row.cost))
            )
        return summary


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()
