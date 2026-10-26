"""埋点接口：前端上报事件；管理员查看按天聚合。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_id, require_admin
from app.core.errors import InvalidInput
from app.infra.analytics_repo import (
    ALLOWED_EVENTS,
    InMemoryAnalyticsRepository,
    SqlAnalyticsRepository,
)

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])


class EventIn(BaseModel):
    name: str = Field(min_length=1, max_length=48)
    session_id: int | None = None
    duration_ms: int | None = Field(default=None, ge=0, le=600_000)
    error_code: str | None = Field(default=None, max_length=64)


def get_repo(request: Request) -> object:
    repo = getattr(request.app.state, "analytics_repo", None)
    if not isinstance(repo, (SqlAnalyticsRepository, InMemoryAnalyticsRepository)):
        raise InvalidInput("埋点服务未初始化", code="ANALYTICS_UNAVAILABLE")
    return repo


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def record_event(
    payload: EventIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    repo: Annotated[object, Depends(get_repo)],
) -> None:
    if payload.name not in ALLOWED_EVENTS:
        raise InvalidInput(f"未知事件：{payload.name}", code="ANALYTICS_UNKNOWN_EVENT")
    await repo.record(
        user_id,
        payload.name,
        session_id=payload.session_id,
        duration_ms=payload.duration_ms,
        error_code=payload.error_code,
    )


@router.get("/summary")
async def summary(
    _admin: Annotated[str, Depends(require_admin)],
    repo: Annotated[object, Depends(get_repo)],
    days: int = 7,
) -> list[dict[str, object]]:
    return await repo.summary(max(1, min(days, 90)))
