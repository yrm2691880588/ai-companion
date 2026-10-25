"""数据导出：一次性返回当前账号的伴侣、人设、会话、消息与记忆。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user_id

router = APIRouter(prefix="/v1/me", tags=["export"])


@router.get("/export")
async def export_data(
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    companions_repo = request.app.state.companion_repo
    chat_repo = request.app.state.chat_repo
    memory_service = request.app.state.memory_service

    exported: list[dict[str, Any]] = []
    for companion in await companions_repo.list(user_id):
        sessions = await chat_repo.list_sessions(user_id, companion.id)
        session_items: list[dict[str, Any]] = []
        for session in sessions:
            messages = await chat_repo.list_messages(user_id, session.id, limit=10_000)
            session_items.append(
                {
                    "id": session.id,
                    "title": session.title,
                    "created_at": session.created_at.isoformat(),
                    "messages": [
                        {
                            "seq": item.seq,
                            "role": item.role,
                            "content": item.content,
                            "created_at": item.created_at.isoformat(),
                        }
                        for item in messages
                    ],
                }
            )
        memories = await memory_service.list(user_id, companion.id, limit=500)
        exported.append(
            {
                "id": companion.id,
                "name": companion.name,
                "persona_version": companion.current_version,
                "persona": companion.persona.model_dump(mode="json"),
                "sessions": session_items,
                "memories": [
                    {
                        "type": item.type,
                        "content": item.content,
                        "confidence": item.confidence,
                        "created_at": item.created_at.isoformat(),
                    }
                    for item in memories
                ],
            }
        )

    return {
        "user_id": user_id,
        "exported_at": datetime.now(UTC).isoformat(),
        "companions": exported,
    }
