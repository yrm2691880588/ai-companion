"""用量统计的响应模型。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class UsageTotalsOut(BaseModel):
    calls: int = 0
    ok_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    hit_ratio: float = 0.0
    cost_cny: float = 0.0


class ModelUsageOut(BaseModel):
    model_key: str
    totals: UsageTotalsOut
    avg_first_token_ms: int | None = None


class DailyUsageOut(BaseModel):
    day: date
    calls: int = 0
    cost_cny: float = 0.0


class UsageSummaryOut(BaseModel):
    days: int
    totals: UsageTotalsOut = Field(default_factory=UsageTotalsOut)
    by_model: list[ModelUsageOut] = Field(default_factory=list)
    daily: list[DailyUsageOut] = Field(default_factory=list)
