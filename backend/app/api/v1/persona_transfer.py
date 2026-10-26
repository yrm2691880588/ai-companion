"""人设导入导出：导出 10 字段 JSON，导入时校验后创建。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.api.deps import get_companion_service, get_current_user_id
from app.api.v1.companion_schemas import CompanionOut
from app.api.v1.companions import _out
from app.domain.companions import CompanionService
from app.domain.persona import Persona

router = APIRouter(prefix="/v1/personas", tags=["persona-transfer"])

EXPORT_FORMAT = "ai-companion-persona"
EXPORT_VERSION = 1


class PersonaExportOut(BaseModel):
    format: str = EXPORT_FORMAT
    version: int = EXPORT_VERSION
    exported_at: str
    persona: dict[str, Any]


class PersonaImportIn(BaseModel):
    """兼容两种格式：直接给人设对象，或带 format/version 的导出文件。"""

    persona: Persona | None = None
    format: str | None = Field(default=None, max_length=64)
    version: int | None = None
    name: str | None = Field(default=None, max_length=20)

    def resolved_persona(self) -> Persona:
        if self.persona is None:
            raise ValueError("缺少 persona 字段")
        if self.format not in (None, EXPORT_FORMAT):
            raise ValueError(f"不支持的文件格式：{self.format}")
        if self.version is not None and self.version > EXPORT_VERSION:
            raise ValueError(f"文件版本过新：{self.version}")
        return self.persona


@router.post("/import", response_model=CompanionOut, status_code=status.HTTP_201_CREATED)
async def import_persona(
    payload: PersonaImportIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> CompanionOut:
    """从 JSON 导入人设并创建伴侣；字段非法时返回 422 与具体原因。"""
    try:
        persona = payload.resolved_persona()
    except ValueError as exc:
        from app.core.errors import InvalidInput

        raise InvalidInput(str(exc), code="IMPORT_INVALID") from exc
    record = await service.create(user_id, persona, name=payload.name)
    return _out(record)
