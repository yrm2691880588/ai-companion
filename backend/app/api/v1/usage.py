"""用量统计接口：按模型汇总调用次数、token、缓存命中、成本与首字延迟。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import get_current_user_id
from app.api.v1.usage_schemas import (
    DailyUsageOut,
    ModelUsageOut,
    UsageSummaryOut,
    UsageTotalsOut,
)
from app.core.errors import AppError
from app.domain.usage import UsageSummary

router = APIRouter(prefix="/v1/me/usage", tags=["usage"])


def _totals_out(totals: object) -> UsageTotalsOut:
    return UsageTotalsOut(
        calls=totals.calls,  # type: ignore[attr-defined]
        ok_calls=totals.ok_calls,  # type: ignore[attr-defined]
        input_tokens=totals.input_tokens,  # type: ignore[attr-defined]
        output_tokens=totals.output_tokens,  # type: ignore[attr-defined]
        cache_hit_tokens=totals.cache_hit_tokens,  # type: ignore[attr-defined]
        cache_miss_tokens=totals.cache_miss_tokens,  # type: ignore[attr-defined]
        hit_ratio=round(totals.hit_ratio, 4),  # type: ignore[attr-defined]
        cost_cny=round(totals.cost_cny, 6),  # type: ignore[attr-defined]
    )


def _to_out(summary: UsageSummary) -> UsageSummaryOut:
    return UsageSummaryOut(
        days=summary.days,
        totals=_totals_out(summary.totals),
        by_model=[
            ModelUsageOut(
                model_key=item.model_key,
                totals=_totals_out(item.totals),
                avg_first_token_ms=(
                    round(item.avg_first_token_ms) if item.avg_first_token_ms is not None else None
                ),
            )
            for item in summary.by_model
        ],
        daily=[
            DailyUsageOut(
                day=item.day,
                calls=item.calls,
                cost_cny=round(item.cost_micros / 1_000_000, 6),
            )
            for item in summary.daily
        ],
    )


@router.get("/models", response_model=UsageSummaryOut)
async def usage_by_model(
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> UsageSummaryOut:
    repo = getattr(request.app.state, "usage_repo", None)
    if repo is None:
        raise AppError(code="USAGE_UNAVAILABLE", message="用量统计暂不可用", status_code=503)
    try:
        summary = await repo.summary(user_id, days=days)
    except ValueError as exc:
        raise AppError(code="INVALID_DAYS", message=str(exc), status_code=422) from exc
    return _to_out(summary)
