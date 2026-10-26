"""试聊接口：草稿人设 3 轮，不写正式库。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_id
from app.api.v1.personas import request_id
from app.core.errors import AppError
from app.domain.chat import ChatDelta, ChatDone, ChatMeta
from app.domain.persona import Persona
from app.domain.trial import TrialService

router = APIRouter(prefix="/v1/trial", tags=["trial"])


class TrialIn(BaseModel):
    persona: Persona
    content: str = Field(min_length=1, max_length=2000)
    trial_id: str | None = Field(default=None, max_length=32)


def get_trial_service(request: Request) -> TrialService:
    service = getattr(request.app.state, "trial_service", None)
    if not isinstance(service, TrialService):
        raise AppError(code="TRIAL_UNAVAILABLE", message="试聊服务未初始化", status_code=503)
    return service


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def trial_chat(
    payload: TrialIn,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[TrialService, Depends(get_trial_service)],
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in service.chat(
                user_id,
                payload.persona,
                payload.content,
                trial_id=payload.trial_id,
                request_id=request_id(request),
            ):
                if isinstance(event, ChatMeta):
                    yield _sse("meta", {"trial_id": event.trial_id})
                elif isinstance(event, ChatDelta):
                    yield _sse("delta", {"text": event.text})
                elif isinstance(event, ChatDone):
                    yield _sse(
                        "done",
                        {
                            "model": event.model_key,
                            "input_tokens": event.usage.input_tokens,
                            "output_tokens": event.usage.completion_tokens,
                        },
                    )
        except AppError as exc:
            yield _sse("error", {"code": exc.code, "message": exc.message})
        except Exception:
            yield _sse("error", {"code": "TRIAL_FAILED", "message": "试聊失败，请重试"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
