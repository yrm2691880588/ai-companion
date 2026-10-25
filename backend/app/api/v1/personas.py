"""人设接口：字段说明与「一句话生成人设」。"""

from __future__ import annotations

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_companion_service, get_current_user_id
from app.api.v1.companion_schemas import (
    DimensionMetaOut,
    PersonaDraftIn,
    PersonaDraftOut,
    PersonaSchemaOut,
)
from app.domain.companions import CompanionService
from app.domain.persona import CURRENT_SCHEMA_VERSION, DIMENSION_META, MAX_AGE, MIN_AGE

router = APIRouter(prefix="/v1/personas", tags=["personas"])


def request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id") or str(uuid4())


@router.get("/schema", response_model=PersonaSchemaOut)
def persona_schema() -> PersonaSchemaOut:
    """返回 7 个维度的字段定义，供前端渲染表单与校验。"""
    return PersonaSchemaOut(
        schema_version=CURRENT_SCHEMA_VERSION,
        dimensions=[DimensionMetaOut(**item) for item in DIMENSION_META],
        age_min=MIN_AGE,
        age_max=MAX_AGE,
    )


@router.post("/draft", response_model=PersonaDraftOut)
async def generate_draft(
    payload: PersonaDraftIn,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> PersonaDraftOut:
    """用一句自然语言描述生成完整人设（不落库，用户确认后再创建）。"""
    persona, result = await service.generate_persona(
        user_id, payload.description, request_id(request)
    )
    return PersonaDraftOut(
        persona=persona,
        model_key=result.model_key,
        cost_cny=float(result.cost_cny),
    )
