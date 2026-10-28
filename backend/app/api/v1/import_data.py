"""数据导入：把整库导出文件导回本机，按 ULID 去重。

语义（与用户确认的方案一致）：
- **只做伴侣级去重**：同一 ULID 的伴侣已存在就跳过整棵子树，不写入会话与消息；
- 冲突时不覆盖、不报错，只统计并报告；
- 导入前校验 format/version，避免把别的文件塞进来；
- 单项失败不影响其它伴侣，逐项记录原因。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import get_companion_service, get_current_user_id
from app.core.errors import InvalidInput
from app.domain.companions import CompanionService
from app.domain.persona import Persona

router = APIRouter(prefix="/v1/me", tags=["import"])

EXPORT_FORMAT = "ai-companion-export"
SUPPORTED_VERSION = 2


class CompanionImportIn(BaseModel):
    format: str = Field(default=EXPORT_FORMAT, max_length=64)
    version: int = SUPPORTED_VERSION
    companions: list[dict[str, Any]] = Field(default_factory=list, max_length=200)


class ImportReport(BaseModel):
    created: list[str] = Field(default_factory=list, description="新建的伴侣 ULID")
    skipped: list[str] = Field(default_factory=list, description="因 ULID 已存在而跳过的")
    failed: list[dict[str, str]] = Field(default_factory=list, description="逐项失败原因")

    @property
    def summary(self) -> dict[str, int]:
        return {
            "created": len(self.created),
            "skipped": len(self.skipped),
            "failed": len(self.failed),
        }


@router.post("/import", response_model=ImportReport)
async def import_data(
    payload: CompanionImportIn,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> ImportReport:
    """把导出文件里的伴侣导入本机；同 ULID 跳过并计入报告。"""
    if payload.format != EXPORT_FORMAT:
        raise InvalidInput(
            f"不是本产品的数据导出文件（format={payload.format}）", code="IMPORT_FORMAT"
        )
    if payload.version > SUPPORTED_VERSION:
        raise InvalidInput(
            f"导出文件版本 {payload.version} 高于当前支持的 {SUPPORTED_VERSION}",
            code="IMPORT_VERSION",
        )

    repo = request.app.state.companion_repo
    report = ImportReport()

    for index, item in enumerate(payload.companions):
        ulid = str(item.get("ulid") or "").strip()
        try:
            if ulid:
                existing = await repo.find_by_ulid(user_id, ulid)
                if existing is not None:
                    report.skipped.append(ulid)
                    continue

            raw_persona = item.get("persona")
            if not isinstance(raw_persona, dict):
                raise InvalidInput("缺少 persona", code="IMPORT_INVALID")
            persona = Persona.model_validate(raw_persona)
            name = str(item.get("name") or persona.name)

            created = await service.create(user_id, persona, name=name, ulid=ulid or None)
            report.created.append(created.ulid)
        except InvalidInput as exc:
            report.failed.append({"index": str(index), "reason": exc.message})
        except Exception as exc:  # 单项失败不该中断整包导入
            report.failed.append({"index": str(index), "reason": str(exc)[:200]})

    return report


@router.get("/import/preview")
async def import_preview(
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """给前端用的说明：当前支持的导入格式与去重规则。"""
    return {
        "format": EXPORT_FORMAT,
        "version": SUPPORTED_VERSION,
        "dedupe": "companion-ulid",
        "conflict": "skip-and-report",
        "note": "同 ULID 的伴侣已存在时整棵子树跳过，不覆盖现有数据",
        "generated_at": datetime.now().isoformat(),
    }
