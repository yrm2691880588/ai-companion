"""试聊：用草稿人设聊最多 3 轮，不写正式库、不产生记忆、不扣额度。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.core.errors import AppError, InvalidInput
from app.core.ids import new_ulid
from app.domain.chat import SAFETY_NOTE, ChatDelta, ChatDone, ChatEvent, ChatMeta
from app.domain.persona import Persona, compile_prompt
from app.domain.safety import assess_input
from app.domain.usage import CallContext, aggregate_usage
from app.infra.llm.types import Message, Role, TaskName, Usage

MAX_TRIAL_TURNS = 3
MAX_TRIAL_SESSIONS = 200


@dataclass(slots=True)
class TrialTurn:
    role: str
    content: str


@dataclass(slots=True)
class TrialSession:
    id: str
    persona: Persona
    turns: list[TrialTurn] = field(default_factory=list)
    created_at: float = 0.0


class TrialService:
    """内存态试聊；进程重启即清空，符合“不落库”。"""

    def __init__(
        self, streamer: object, *, daily_limit: int = 20, profiles: object | None = None
    ) -> None:
        self._streamer = streamer
        self._sessions: dict[str, TrialSession] = {}
        self._lock = asyncio.Lock()
        self._daily_limit = max(daily_limit, 1)
        self._profiles = profiles
        self._daily: dict[tuple[str, str], int] = {}

    async def chat(
        self,
        user_id: str,
        persona: Persona,
        content: str,
        *,
        trial_id: str | None,
        request_id: str,
    ) -> AsyncIterator[ChatEvent]:
        text = (content or "").strip()
        if not text:
            raise InvalidInput("消息不能为空")
        if len(text) > 2000:
            raise InvalidInput("单条消息最多 2000 字")
        async with self._lock:
            if trial_id and trial_id not in self._sessions:
                raise AppError(
                    code="TRIAL_NOT_FOUND",
                    message="试聊已过期，请重新开始",
                    status_code=404,
                )
            today = time.strftime("%Y-%m-%d")
            key = (user_id, today)
            if not trial_id and self._daily.get(key, 0) >= self._daily_limit:
                raise AppError(
                    code="TRIAL_DAILY_LIMIT",
                    message=f"今天试聊次数已用完（{self._daily_limit} 次），明天再来",
                    status_code=429,
                )
            session = self._sessions.get(trial_id) if trial_id else None
            if session is None:
                self._daily[key] = self._daily.get(key, 0) + 1
                session = TrialSession(id=new_ulid(), persona=persona, created_at=time.time())
                self._sessions[session.id] = session
                self._trim()
            elif session.persona != persona:
                raise AppError(
                    code="TRIAL_PERSONA_CHANGED",
                    message="试聊中不能更换人设，请重新开始",
                    status_code=409,
                )
            if len(session.turns) >= MAX_TRIAL_TURNS * 2:
                raise AppError(
                    code="TRIAL_LIMIT",
                    message=f"试聊最多 {MAX_TRIAL_TURNS} 轮，去创建她继续聊吧",
                    status_code=409,
                )
            session.turns.append(TrialTurn(role="user", content=text))
            history = list(session.turns)
            profile_note = ""
            if self._profiles is not None:
                try:
                    profile_note = await self._profiles.prompt_for(  # type: ignore[attr-defined]
                        user_id, 0
                    )
                except Exception:
                    profile_note = ""
            system_prompt = compile_prompt(persona) + profile_note + SAFETY_NOTE
            assessment = assess_input(text)
            if assessment.is_crisis:
                from app.domain.safety import CRISIS_NOTE

                system_prompt += CRISIS_NOTE

        messages = [Message(role=Role.SYSTEM, content=system_prompt)]
        for turn in history:
            role = Role.ASSISTANT if turn.role == "assistant" else Role.USER
            messages.append(Message(role=role, content=turn.content))

        yield ChatMeta(session_id=0, user_message_id=0, trial_id=session.id)
        collected = ""
        usage_parts: list[Usage] = []
        model_key = ""
        try:
            async for chunk in self._streamer.stream(  # type: ignore[attr-defined]
                TaskName.CHAT_MAIN,
                messages,
                context=CallContext(
                    user_id=user_id, request_id=request_id, task=TaskName.CHAT_MAIN
                ),
            ):
                if chunk.model_key:
                    model_key = chunk.model_key
                if chunk.usage is not None:
                    usage_parts.append(chunk.usage)
                if chunk.delta:
                    collected += chunk.delta
                    yield ChatDelta(chunk.delta)
        except Exception:
            raise
        async with self._lock:
            session.turns.append(TrialTurn(role="assistant", content=collected))
        yield ChatDone(
            assistant_message_id=0,
            model_key=model_key,
            usage=aggregate_usage(usage_parts),
        )

    def _trim(self) -> None:
        if len(self._sessions) <= MAX_TRIAL_SESSIONS:
            return
        oldest = sorted(self._sessions.values(), key=lambda item: item.created_at)[
            : len(self._sessions) - MAX_TRIAL_SESSIONS
        ]
        for item in oldest:
            self._sessions.pop(item.id, None)
