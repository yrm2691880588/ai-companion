"""每日额度接口。"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.deps import get_current_user_id
from app.domain.quota import QuotaService

router = APIRouter(prefix="/v1/me", tags=["quota"])


class QuotaOut(BaseModel):
    day: date
    used: int
    limit: int
    remaining: int


def get_quota_service(request: Request) -> QuotaService:
    service = getattr(request.app.state, "quota_service", None)
    if not isinstance(service, QuotaService):
        raise RuntimeError("额度服务尚未初始化")
    return service


@router.get("/quota", response_model=QuotaOut)
async def get_quota(
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[QuotaService, Depends(get_quota_service)],
) -> QuotaOut:
    state = await service.status(user_id)
    return QuotaOut(day=state.day, used=state.used, limit=state.limit, remaining=state.remaining)
