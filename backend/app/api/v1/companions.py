"""伴侣接口：创建、列表、详情、人设编辑与单维重写。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, status

from app.api.deps import get_companion_service, get_current_user_id, get_deletion_service
from app.api.v1.companion_schemas import (
    AvatarIn,
    CompanionCreateIn,
    CompanionOut,
    DeriveIn,
    DimensionPatchIn,
    DimensionRegenerateIn,
    DimensionRegenerateOut,
    PersonaPutIn,
    PersonaVersionOut,
    TemplateCreateIn,
    VoiceIn,
)
from app.api.v1.personas import request_id
from app.domain.companions import CompanionRecord, CompanionService
from app.domain.deletion import DeletionService

router = APIRouter(prefix="/v1/companions", tags=["companions"])


def _out(record: CompanionRecord) -> CompanionOut:
    return CompanionOut(
        id=record.id,
        name=record.name,
        current_version=record.current_version,
        persona=record.persona,
        memory_enabled=record.memory_enabled,
        avatar=record.avatar,
        derived_from=record.derived_from,
        voice_id=record.voice_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=list[CompanionOut])
async def list_companions(
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> list[CompanionOut]:
    records = await service.list(user_id)
    return [_out(record) for record in records]


@router.post("", response_model=CompanionOut, status_code=status.HTTP_201_CREATED)
async def create_companion(
    payload: CompanionCreateIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> CompanionOut:
    record = await service.create(user_id, payload.persona, name=payload.name)
    return _out(record)


@router.post("/from-template", response_model=CompanionOut, status_code=status.HTTP_201_CREATED)
async def create_from_template(
    payload: TemplateCreateIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> CompanionOut:
    """基于官方模板创建伴侣（可只改名字，其余沿用模板人设）。"""
    record = await service.create_from_template(user_id, payload.template_key, name=payload.name)
    return _out(record)


@router.get("/{companion_id}", response_model=CompanionOut)
async def get_companion(
    companion_id: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> CompanionOut:
    return _out(await service.get(user_id, companion_id))


@router.put("/{companion_id}/persona", response_model=CompanionOut)
async def replace_persona(
    companion_id: int,
    payload: PersonaPutIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> CompanionOut:
    """整体保存人设：生成新版本，历史版本保留，从下一条回复开始生效。"""
    return _out(await service.replace_persona(user_id, companion_id, payload.persona))


@router.get("/{companion_id}/personas", response_model=list[PersonaVersionOut])
async def list_persona_versions(
    companion_id: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> list[PersonaVersionOut]:
    """人设的历史版本，最新的在前。"""
    versions = await service.list_persona_versions(user_id, companion_id)
    return [
        PersonaVersionOut(version=item.version, persona=item.persona, created_at=item.created_at)
        for item in versions
    ]


@router.post("/{companion_id}/personas/{version}/restore", response_model=CompanionOut)
async def restore_persona_version(
    companion_id: int,
    version: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> CompanionOut:
    """把某个历史版本还原成新版本（历史不丢，还原本身也可撤销）。"""
    return _out(await service.restore_persona_version(user_id, companion_id, version))


@router.patch("/{companion_id}/persona", response_model=CompanionOut)
async def patch_persona_dimension(
    companion_id: int,
    payload: DimensionPatchIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> CompanionOut:
    """只改某一个人设维度，保存后立即生效（生成新版本）。"""
    return _out(
        await service.patch_dimension(user_id, companion_id, payload.dimension, payload.value)
    )


@router.post(
    "/{companion_id}/persona/regenerate",
    response_model=DimensionRegenerateOut,
)
async def regenerate_dimension(
    companion_id: int,
    payload: DimensionRegenerateIn,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> DimensionRegenerateOut:
    """让 AI 只重写一个维度，返回建议值（需用户确认后才保存）。"""
    value, result = await service.regenerate_dimension(
        user_id, companion_id, payload.dimension, payload.hint, request_id(request)
    )
    return DimensionRegenerateOut(
        dimension=payload.dimension,
        value=value,
        model_key=result.model_key,
        cost_cny=float(result.cost_cny),
    )


@router.put("/{companion_id}/avatar", response_model=CompanionOut)
async def set_avatar(
    companion_id: int,
    payload: AvatarIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> CompanionOut:
    """上传/清除头像：data URL（PNG/JPEG/WebP，≤300KB）。"""
    record = await service.set_avatar(user_id, companion_id, payload.avatar)
    return _out(record)


@router.post(
    "/{companion_id}/derive", response_model=CompanionOut, status_code=status.HTTP_201_CREATED
)
async def derive_companion(
    companion_id: int,
    payload: DeriveIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> CompanionOut:
    """基于已有伴侣的人设创建新伴侣：只复制人设，不复制会话/记忆/头像。"""
    record = await service.derive(user_id, companion_id, payload.persona, name=payload.name)
    return _out(record)


@router.delete("/{companion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_companion(
    companion_id: int,
    confirm_name: Annotated[str, Query(min_length=1, max_length=20)],
    background: BackgroundTasks,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
    deletion: Annotated[DeletionService, Depends(get_deletion_service)],
) -> Response:
    """删除伴侣：软删后立即排队硬清（会话/消息/记忆/演练一并删除）。"""
    await service.delete(user_id, companion_id, confirm_name)
    job = await deletion.enqueue(user_id, companion_id)
    background.add_task(deletion.run_job, job.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{companion_id}/voice", response_model=CompanionOut)
async def set_companion_voice(
    companion_id: int,
    payload: VoiceIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[CompanionService, Depends(get_companion_service)],
) -> CompanionOut:
    record = await service.set_voice(user_id, companion_id, payload.voice_id)
    return _out(record)
