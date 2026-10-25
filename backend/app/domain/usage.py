"""调用记账的领域类型：一次调用（含失败尝试）的记录与汇总。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Protocol

from app.infra.llm.types import TaskName, Usage


@dataclass(frozen=True, slots=True)
class CallContext:
    """一次请求的上下文，用于把用量记到某个用户名下。"""

    user_id: str
    request_id: str
    task: TaskName | str


@dataclass(frozen=True, slots=True)
class CallRecord:
    user_id: str
    task: str
    request_id: str
    provider_key: str
    model_key: str
    attempt_no: int = 1
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    cost_micros: int = 0
    first_token_ms: int | None = None
    total_ms: int | None = None
    status: str = "ok"  # ok | error | aborted | blocked
    error_code: str | None = None
    created_at: datetime | None = None

    @property
    def input_tokens(self) -> int:
        return self.prompt_tokens or (self.cache_hit_tokens + self.cache_miss_tokens)

    @property
    def hit_ratio(self) -> float:
        total = self.cache_hit_tokens + self.cache_miss_tokens
        return self.cache_hit_tokens / total if total else 0.0

    @property
    def cost_cny(self) -> float:
        return self.cost_micros / 1_000_000


@dataclass(slots=True)
class UsageTotals:
    calls: int = 0
    ok_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    cost_micros: int = 0

    @property
    def hit_ratio(self) -> float:
        total = self.cache_hit_tokens + self.cache_miss_tokens
        return self.cache_hit_tokens / total if total else 0.0

    @property
    def cost_cny(self) -> float:
        return self.cost_micros / 1_000_000


@dataclass(slots=True)
class ModelUsage:
    model_key: str
    totals: UsageTotals = field(default_factory=UsageTotals)
    avg_first_token_ms: float | None = None


@dataclass(slots=True)
class DailyUsage:
    day: date
    calls: int = 0
    cost_micros: int = 0


@dataclass(slots=True)
class UsageSummary:
    days: int
    totals: UsageTotals = field(default_factory=UsageTotals)
    by_model: list[ModelUsage] = field(default_factory=list)
    daily: list[DailyUsage] = field(default_factory=list)


class UsageRecorder(Protocol):
    async def save(self, record: CallRecord) -> None: ...


class UsageRepository(UsageRecorder, Protocol):
    async def summary(self, user_id: str, *, days: int) -> UsageSummary: ...


class InMemoryUsageRepository:
    """测试与本地演示用的内存实现。"""

    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    async def save(self, record: CallRecord) -> None:
        self.records.append(record)

    async def summary(self, user_id: str, *, days: int) -> UsageSummary:
        mine = [record for record in self.records if record.user_id == user_id]
        summary = UsageSummary(days=days)
        by_model: dict[str, ModelUsage] = {}
        daily: dict[date, DailyUsage] = {}
        first_token_samples: dict[str, list[int]] = {}

        def add_totals(target: UsageTotals, record: CallRecord) -> None:
            target.calls += 1
            target.ok_calls += 1 if record.status == "ok" else 0
            target.input_tokens += record.input_tokens
            target.output_tokens += record.completion_tokens
            target.cache_hit_tokens += record.cache_hit_tokens
            target.cache_miss_tokens += record.cache_miss_tokens
            target.cost_micros += record.cost_micros

        for record in mine:
            add_totals(summary.totals, record)
            model = by_model.setdefault(record.model_key, ModelUsage(model_key=record.model_key))
            add_totals(model.totals, record)
            if record.first_token_ms is not None:
                first_token_samples.setdefault(record.model_key, []).append(record.first_token_ms)
            day = (record.created_at or datetime.now(UTC)).date()
            bucket = daily.setdefault(day, DailyUsage(day=day))
            bucket.calls += 1
            bucket.cost_micros += record.cost_micros
        for model_key, samples in first_token_samples.items():
            by_model[model_key].avg_first_token_ms = sum(samples) / len(samples)
        summary.by_model = sorted(
            by_model.values(), key=lambda item: item.totals.calls, reverse=True
        )
        summary.daily = sorted(daily.values(), key=lambda item: item.day)
        return summary


def aggregate_usage(chunks: list[Usage]) -> Usage:
    """把流式过程中的多段 usage 合成一份（Anthropic 会分段给）。"""
    return Usage(
        prompt_tokens=sum(chunk.prompt_tokens for chunk in chunks),
        completion_tokens=sum(chunk.completion_tokens for chunk in chunks),
        cache_hit_tokens=sum(chunk.cache_hit_tokens for chunk in chunks),
        cache_miss_tokens=sum(chunk.cache_miss_tokens for chunk in chunks),
    )
