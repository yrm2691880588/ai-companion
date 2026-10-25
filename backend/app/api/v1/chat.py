"""对话接口：会话、历史消息、SSE 流式回复。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_chat_service, get_current_user_id, get_summary_repo
from app.api.v1.chat_schemas import (
    LatestOut,
    MessageOut,
    SendMessageIn,
    SessionCreateIn,
    SessionOut,
    SessionRenameIn,
    SummaryOut,
)
from app.api.v1.personas import request_id
from app.core.errors import AppError
from app.domain.chat import ChatDelta, ChatDone, ChatMeta, ChatService, MessageRecord, SessionRecord
from app.infra.summary_repo import SummaryRepository

router = APIRouter(prefix="/v1", tags=["chat"])


def _session_out(record: SessionRecord) -> SessionOut:
    return SessionOut(
        id=record.id,
        companion_id=record.companion_id,
        title=record.title,
        state=record.state,
        created_at=record.created_at,
        last_message_at=record.last_message_at,
    )


def _message_out(record: MessageRecord) -> MessageOut:
    return MessageOut(
        id=record.id,
        session_id=record.session_id,
        seq=record.seq,
        role=record.role,
        content=record.content,
        created_at=record.created_at,
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "/companions/{companion_id}/sessions",
    response_model=SessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    companion_id: int,
    payload: SessionCreateIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> SessionOut:
    record = await service.create_session(user_id, companion_id, payload.title)
    return _session_out(record)


@router.get("/companions/{companion_id}/sessions", response_model=list[SessionOut])
async def list_sessions(
    companion_id: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> list[SessionOut]:
    return [_session_out(item) for item in await service.list_sessions(user_id, companion_id)]


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> SessionOut:
    return _session_out(await service.get_session(user_id, session_id))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> Response:
    await service.delete_session(user_id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/sessions/{session_id}", response_model=SessionOut)
async def rename_session(
    session_id: int,
    payload: SessionRenameIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> SessionOut:
    record = await service.rename_session(user_id, session_id, payload.title)
    return _session_out(record)


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> Response:
    await service.delete_message(user_id, message_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions/{session_id}/summary", response_model=SummaryOut)
async def get_session_summary(
    session_id: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
    summaries: Annotated[SummaryRepository, Depends(get_summary_repo)],
) -> SummaryOut:
    """查看这段会话当前的摘要（没有摘要时返回空）。"""
    await service.get_session(user_id, session_id)
    record = await summaries.get(session_id)
    if record is None:
        return SummaryOut(session_id=session_id)
    return SummaryOut(
        session_id=session_id,
        summary=record.summary,
        covered_seq=record.covered_seq,
        updated_at=record.updated_at,
    )


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(
    session_id: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
    before_seq: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[MessageOut]:
    records = await service.list_messages(user_id, session_id, before_seq=before_seq, limit=limit)
    return [_message_out(item) for item in records]


@router.post("/sessions/{session_id}/opener", response_model=MessageOut)
async def open_session(
    session_id: int,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> MessageOut:
    """空会话的第一句由伴侣先开口；已有消息时原样返回第一条。"""
    message = await service.open_session(user_id, session_id, request_id(request))
    return _message_out(message)


@router.get("/companions/{companion_id}/latest", response_model=LatestOut)
async def latest_message(
    companion_id: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> LatestOut:
    message = await service.latest_message(user_id, companion_id)
    if message is None:
        return LatestOut()
    return LatestOut(
        session_id=message.session_id,
        message_id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: int,
    payload: SendMessageIn,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> StreamingResponse:
    """发送消息并以 SSE 流式返回：meta → delta* → done（或 error）。"""

    await service.ensure_quota(user_id)

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in service.stream_reply(
                user_id,
                session_id,
                payload.content,
                request_id(request),
                client_request_id=payload.client_request_id,
            ):
                if isinstance(event, ChatMeta):
                    yield _sse(
                        "meta",
                        {
                            "session_id": event.session_id,
                            "user_message_id": event.user_message_id,
                        },
                    )
                elif isinstance(event, ChatDelta):
                    yield _sse("delta", {"text": event.text})
                elif isinstance(event, ChatDone):
                    yield _sse(
                        "done",
                        {
                            "assistant_message_id": event.assistant_message_id,
                            "model": event.model_key,
                            "input_tokens": event.usage.input_tokens,
                            "output_tokens": event.usage.completion_tokens,
                            "cache_hit_tokens": event.usage.cache_hit_tokens,
                        },
                    )
        except AppError as exc:
            yield _sse("error", {"code": exc.code, "message": exc.message})
        except Exception:
            yield _sse("error", {"code": "STREAM_FAILED", "message": "生成失败，请重试"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/messages/{message_id}/regenerate")
async def regenerate_message(
    message_id: int,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> StreamingResponse:
    """重新生成最后一条助手回复（原地替换，不新增用户消息）。"""
    await service.ensure_quota(user_id)

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in service.regenerate(user_id, message_id, request_id(request)):
                if isinstance(event, ChatMeta):
                    yield _sse(
                        "meta",
                        {
                            "session_id": event.session_id,
                            "user_message_id": event.user_message_id,
                        },
                    )
                elif isinstance(event, ChatDelta):
                    yield _sse("delta", {"text": event.text})
                elif isinstance(event, ChatDone):
                    yield _sse(
                        "done",
                        {
                            "assistant_message_id": event.assistant_message_id,
                            "model": event.model_key,
                            "input_tokens": event.usage.input_tokens,
                            "output_tokens": event.usage.completion_tokens,
                        },
                    )
        except AppError as exc:
            yield _sse("error", {"code": exc.code, "message": exc.message})
        except Exception:
            yield _sse("error", {"code": "REGENERATE_FAILED", "message": "重新生成失败，请重试"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
