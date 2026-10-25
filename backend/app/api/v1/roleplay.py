"""演练接口：场景列表、开始、回合（SSE）、结束复盘。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user_id, get_roleplay_service
from app.api.v1.personas import request_id
from app.api.v1.roleplay_schemas import (
    RunOut,
    RunStartIn,
    RunStartOut,
    ScenarioOut,
    TurnIn,
)
from app.core.errors import AppError
from app.domain.chat import ChatDelta, ChatDone, ChatMeta
from app.domain.roleplay import RoleplayService, RunRecord, Scenario

router = APIRouter(prefix="/v1", tags=["roleplay"])


def _scenario_out(scenario: Scenario) -> ScenarioOut:
    return ScenarioOut(
        key=scenario.key,
        title=scenario.title,
        category=scenario.category,
        role=scenario.role,
        goal=scenario.goal,
        difficulty=scenario.difficulty,
        max_turns=scenario.max_turns,
        opening=scenario.opening,
        tips=scenario.tips,
    )


def _run_out(run: RunRecord) -> RunOut:
    return RunOut(
        id=run.id,
        companion_id=run.companion_id,
        scenario_key=run.scenario_key,
        session_id=run.session_id,
        status=run.status,
        max_turns=run.max_turns,
        turns_played=run.turns_played,
        review=run.review,
        created_at=run.created_at,
        finished_at=run.finished_at,
    )


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/roleplay/scenarios", response_model=list[ScenarioOut])
async def list_scenarios(
    service: Annotated[RoleplayService, Depends(get_roleplay_service)],
    category: Annotated[str | None, Query(max_length=32)] = None,
) -> list[ScenarioOut]:
    return [_scenario_out(item) for item in await service.list_scenarios(category)]


@router.post(
    "/companions/{companion_id}/roleplay",
    response_model=RunStartOut,
    status_code=status.HTTP_201_CREATED,
)
async def start_roleplay(
    companion_id: int,
    payload: RunStartIn,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[RoleplayService, Depends(get_roleplay_service)],
) -> RunStartOut:
    run, _session, opening = await service.start(
        user_id, companion_id, payload.scenario_key, payload.max_turns
    )
    scenario = await service.list_scenarios()
    matched = next(item for item in scenario if item.key == run.scenario_key)
    return RunStartOut(
        **_run_out(run).model_dump(),
        scenario=_scenario_out(matched),
        opening=opening.content,
    )


@router.get("/roleplay/{run_id}", response_model=RunOut)
async def get_run(
    run_id: int,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[RoleplayService, Depends(get_roleplay_service)],
) -> RunOut:
    return _run_out(await service.get(user_id, run_id))


@router.post("/roleplay/{run_id}/turns")
async def send_turn(
    run_id: int,
    payload: TurnIn,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[RoleplayService, Depends(get_roleplay_service)],
) -> StreamingResponse:
    await service.ensure_quota(user_id)

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in service.stream_turn(
                user_id, run_id, payload.content, request_id(request)
            ):
                if isinstance(event, ChatMeta):
                    yield _sse(
                        "meta",
                        {"session_id": event.session_id, "user_message_id": event.user_message_id},
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
            yield _sse("error", {"code": "ROLEPLAY_FAILED", "message": "演练推进失败，请重试"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/roleplay/{run_id}/finish", response_model=RunOut)
async def finish_run(
    run_id: int,
    request: Request,
    user_id: Annotated[str, Depends(get_current_user_id)],
    service: Annotated[RoleplayService, Depends(get_roleplay_service)],
) -> RunOut:
    run = await service.finish(user_id, run_id, request_id(request))
    return _run_out(run)
