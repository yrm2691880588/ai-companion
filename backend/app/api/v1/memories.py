"""记忆接口：查看、删除、总开关与手动抽取。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import get_chat_service, get_companion_service, get_current_user_id
from app.api.v1.memories_schemas import MemoryOut, MemorySettingsIn, MemorySettingsOut
from app.api.v1.personas import request_id
from app.core.errors import AppError
from app.domain.chat import ChatService
from app.domain.companions import CompanionService
from app.domain.memory import TYPE_LABELS, MemoryRecord, MemoryService, MemoryType

router = APIRouter(prefix="/v1", tags=["memories"])


def _to_out(record: MemoryRecord) -> MemoryOut:
    return MemoryOut(
        id=record.id,
        type=record.type,
        type_label=TYPE_LABELS.get(MemoryType(record.type), record.type),
        content=record.content,
        confidence=record.confidence,
        source_session_id=record.source_session_id,
        quote=record.quote,
        created_at=record.created_at,
        last_used_at=record.last_used_at,
    )


def get_memory_service(request: Request) -> MemoryService:
    service = getattr(request.app.state, "memory_service", None)
    if not isinstance(service, MemoryService):
        raise AppError(code="MEMORY_UNAVAILABLE", message="记忆服务不可用", status_code=503)
    return service


MemoryDep = Annotated[MemoryService, Depends(get_memory_service)]


@router.get("/companions/{companion_id}/memories", response_model=list[MemoryOut])
async def list_memories(
    companion_id: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: MemoryDep,
    companions: Annotated[CompanionService, Depends(get_companion_service)],
    type: Annotated[str | None, Query(max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[MemoryOut]:
    await companions.get(user_id, companion_id)  # 校验归属，别人的伴侣直接 404
    records = await service.list(user_id, companion_id, type=type, limit=limit)
    return [_to_out(item) for item in records]


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: MemoryDep,
) -> None:
    await service.delete(user_id, memory_id)


@router.put(
    "/companions/{companion_id}/memory-settings",
    response_model=MemorySettingsOut,
)
async def update_memory_settings(
    companion_id: int,
    payload: MemorySettingsIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    companions: Annotated[CompanionService, Depends(get_companion_service)],
) -> MemorySettingsOut:
    record = await companions.set_memory_enabled(user_id, companion_id, payload.enabled)
    return MemorySettingsOut(companion_id=record.id, enabled=record.memory_enabled)


@router.post("/sessions/{session_id}/memories/extract", response_model=list[MemoryOut])
async def extract_memories(
    session_id: int,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    memories: MemoryDep,
    chat: Annotated[ChatService, Depends(get_chat_service)],
    limit: Annotated[int, Query(ge=2, le=20)] = 6,
) -> list[MemoryOut]:
    session = await chat.get_session(user_id, session_id)
    messages = await chat.list_messages(user_id, session_id, limit=limit)
    turns = [(item.role, item.content) for item in messages]
    created = await memories.extract(
        user_id, session.companion_id, session_id, turns, request_id(request)
    )
    return [_to_out(item) for item in created]
