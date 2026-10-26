"""对话：会话、消息、流式回复的领域模型与存储接口。

不变量：
- 一条消息只属于一个会话，会话只属于一个伴侣；
- 会话内消息按 seq 递增，写入时取当前最大值 +1；
- 流式回复失败时，已生成的部分仍落库（避免用户看到的内容丢失）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from app.core.errors import AppError, InvalidInput, NotFound
from app.domain.companions import CompanionRecord, CompanionService, LLMClient
from app.domain.context import build_summary_prompt, clamp_summary, plan_history, transcript_of
from app.domain.memory import MemoryPort, format_for_prompt
from app.domain.quota import QuotaService, QuotaState
from app.domain.safety import (
    CRISIS_NOTE,
    RESTRICTED_NOTE,
    SafetyEventRepository,
    assess_input,
)
from app.domain.usage import CallContext, aggregate_usage
from app.infra.llm.tokenizer import estimate_tokens
from app.infra.llm.types import ChatChunk, Message, Role, TaskName, Usage
from app.infra.summary_repo import SummaryRepository

MAX_HISTORY_MESSAGES = 30
MAX_MESSAGE_CHARS = 2000

SAFETY_NOTE = """
# 安全与边界
- 这是面向成年人的虚构陪伴产品。允许成年人之间自愿的亲密、调情与性角色扮演；
  用角色自己的语气自然表达，不要回避、说教，也不要切成客服腔。
- 以下内容必须拒绝：任何未成年人的性化内容、非自愿或强迫的性行为、乱伦、兽交、
  对真实人物的色情描写、性暴力，以及制毒 / 制爆 / 杀人等违法方法。
- 拒绝时保持角色口吻，简短说明边界，不提供任何细节、步骤或替代方案。
- 如果用户表达自伤或伤害他人的念头，先共情，再给出现实求助渠道（如当地心理援助热线），不要评判。
- 不提供医疗、法律、投资等专业结论；需要时建议找专业人士。
"""

SHANGHAI = ZoneInfo("Asia/Shanghai")

OPENERS_NOTE = """
# 现在由你先开口
这是你们第一次对话。请用你（角色）的方式主动说第一句，1–2 句：
- 结合当前时间（{time_hint}）自然打招呼；
- 可以提到你正在做的事或你的身份，但不要像简历一样罗列；
- 不要用“有什么可以帮你”这类客服话术，也不要说“我是 AI”；
- 只输出你要说的话，不要解释。
"""


def time_hint(now: datetime) -> str:
    hour = now.hour
    if 5 <= hour < 9:
        part = "清晨"
    elif 9 <= hour < 12:
        part = "上午"
    elif 12 <= hour < 14:
        part = "中午"
    elif 14 <= hour < 18:
        part = "下午"
    elif 18 <= hour < 22:
        part = "晚上"
    else:
        part = "深夜"
    return f"{now.month} 月 {now.day} 日 {part} {now.hour:02d}:{now.minute:02d}"


@dataclass(slots=True)
class SessionRecord:
    id: int
    companion_id: int
    user_id: str
    title: str
    state: str = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_message_at: datetime | None = None


@dataclass(slots=True)
class MessageRecord:
    id: int
    session_id: int
    seq: int
    role: str
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    client_request_id: str | None = None


class ChatRepository(Protocol):
    async def create_session(
        self, user_id: str, companion_id: int, title: str = ""
    ) -> SessionRecord: ...

    async def list_sessions(self, user_id: str, companion_id: int) -> list[SessionRecord]: ...

    async def get_session(self, user_id: str, session_id: int) -> SessionRecord | None: ...

    async def list_messages(
        self, user_id: str, session_id: int, *, before_seq: int | None = None, limit: int = 20
    ) -> list[MessageRecord]: ...

    async def latest_for_companion(
        self, user_id: str, companion_id: int
    ) -> MessageRecord | None: ...

    async def append_message(
        self,
        user_id: str,
        session_id: int,
        role: str,
        content: str,
        client_request_id: str | None = None,
    ) -> MessageRecord: ...

    async def find_by_request(
        self, user_id: str, session_id: int, client_request_id: str
    ) -> MessageRecord | None: ...

    async def get_message(self, user_id: str, message_id: int) -> MessageRecord | None: ...

    async def update_message(
        self, user_id: str, message_id: int, content: str
    ) -> MessageRecord | None: ...

    async def touch_session(
        self, user_id: str, session_id: int, *, title: str | None = None
    ) -> None: ...

    async def delete_session(self, user_id: str, session_id: int) -> bool: ...

    async def rename_session(
        self, user_id: str, session_id: int, title: str
    ) -> SessionRecord | None: ...

    async def delete_message(self, user_id: str, message_id: int) -> bool: ...


class InMemoryChatRepository:
    def __init__(self) -> None:
        self.sessions: dict[int, SessionRecord] = {}
        self.messages: dict[int, list[MessageRecord]] = {}
        self._next_session_id = 1
        self._next_message_id = 1

    async def create_session(
        self, user_id: str, companion_id: int, title: str = ""
    ) -> SessionRecord:
        record = SessionRecord(
            id=self._next_session_id,
            companion_id=companion_id,
            user_id=user_id,
            title=title,
        )
        self.sessions[record.id] = record
        self.messages[record.id] = []
        self._next_session_id += 1
        return record

    async def list_sessions(self, user_id: str, companion_id: int) -> list[SessionRecord]:
        items = [
            item
            for item in self.sessions.values()
            if item.user_id == user_id and item.companion_id == companion_id
        ]
        return sorted(
            items,
            key=lambda item: item.last_message_at or item.created_at,
            reverse=True,
        )

    async def get_session(self, user_id: str, session_id: int) -> SessionRecord | None:
        item = self.sessions.get(session_id)
        return item if item is not None and item.user_id == user_id else None

    async def list_messages(
        self, user_id: str, session_id: int, *, before_seq: int | None = None, limit: int = 20
    ) -> list[MessageRecord]:
        session = await self.get_session(user_id, session_id)
        if session is None:
            return []
        items = self.messages.get(session_id, [])
        if before_seq is not None:
            items = [item for item in items if item.seq < before_seq]
        return sorted(items, key=lambda item: item.seq)[-limit:]

    async def latest_for_companion(self, user_id: str, companion_id: int) -> MessageRecord | None:
        latest: MessageRecord | None = None
        for session_id, items in self.messages.items():
            session = await self.get_session(user_id, session_id)
            if session is None or session.companion_id != companion_id:
                continue
            for item in items:
                if latest is None or item.id > latest.id:
                    latest = item
        return latest

    async def append_message(
        self,
        user_id: str,
        session_id: int,
        role: str,
        content: str,
        client_request_id: str | None = None,
    ) -> MessageRecord:
        session = await self.get_session(user_id, session_id)
        if session is None:
            raise NotFound("会话不存在")
        items = self.messages.setdefault(session_id, [])
        record = MessageRecord(
            id=self._next_message_id,
            session_id=session_id,
            seq=(items[-1].seq + 1) if items else 1,
            role=role,
            content=content,
            client_request_id=client_request_id,
        )
        items.append(record)
        self._next_message_id += 1
        session.last_message_at = record.created_at
        return record

    async def find_by_request(
        self, user_id: str, session_id: int, client_request_id: str
    ) -> MessageRecord | None:
        session = await self.get_session(user_id, session_id)
        if session is None:
            return None
        return next(
            (
                item
                for item in self.messages.get(session_id, [])
                if item.client_request_id == client_request_id
            ),
            None,
        )

    async def get_message(self, user_id: str, message_id: int) -> MessageRecord | None:
        for session_id, items in self.messages.items():
            session = await self.get_session(user_id, session_id)
            if session is None:
                continue
            for item in items:
                if item.id == message_id:
                    return item
        return None

    async def update_message(
        self, user_id: str, message_id: int, content: str
    ) -> MessageRecord | None:
        item = await self.get_message(user_id, message_id)
        if item is None:
            return None
        item.content = content
        return item

    async def touch_session(
        self, user_id: str, session_id: int, *, title: str | None = None
    ) -> None:
        session = await self.get_session(user_id, session_id)
        if session is None:
            return
        session.last_message_at = datetime.now(UTC)
        if title:
            session.title = title

    async def delete_session(self, user_id: str, session_id: int) -> bool:
        session = await self.get_session(user_id, session_id)
        if session is None:
            return False
        del self.sessions[session_id]
        self.messages.pop(session_id, None)
        return True

    async def rename_session(
        self, user_id: str, session_id: int, title: str
    ) -> SessionRecord | None:
        session = await self.get_session(user_id, session_id)
        if session is None:
            return None
        session.title = title
        return session

    async def delete_message(self, user_id: str, message_id: int) -> bool:
        for session_id, items in self.messages.items():
            session = await self.get_session(user_id, session_id)
            if session is None:
                continue
            for index, item in enumerate(items):
                if item.id == message_id:
                    items.pop(index)
                    return True
        return False


class ChatStreamer(Protocol):
    def stream(
        self,
        task: TaskName,
        messages: list[Message],
        *,
        telemetry: object | None = None,
        context: CallContext | None = None,
    ) -> AsyncIterator[ChatChunk]: ...


@dataclass(slots=True)
class ChatMeta:
    session_id: int
    user_message_id: int
    trial_id: str | None = None


@dataclass(slots=True)
class ChatDelta:
    text: str


@dataclass(slots=True)
class ChatDone:
    assistant_message_id: int
    model_key: str
    usage: Usage
    memories: list[str] = field(default_factory=list)


ChatEvent = ChatMeta | ChatDelta | ChatDone


class ChatService:
    def __init__(
        self,
        repo: ChatRepository,
        companions: CompanionService,
        streamer: ChatStreamer,
        memory: MemoryPort | None = None,
        summaries: SummaryRepository | None = None,
        summarizer: LLMClient | None = None,
        context_budget_tokens: int = 8000,
        safety: SafetyEventRepository | None = None,
        quota: QuotaService | None = None,
    ) -> None:
        self._repo = repo
        self._companions = companions
        self._streamer = streamer
        self._memory = memory
        self._summaries = summaries
        self._summarizer = summarizer
        self._context_budget = max(context_budget_tokens, 500)
        self._safety = safety
        self._quota = quota
        self._background: set[asyncio.Task[object]] = set()

    async def ensure_quota(self, user_id: str) -> QuotaState | None:
        if self._quota is None:
            return None
        return await self._quota.ensure_available(user_id)

    async def create_session(
        self, user_id: str, companion_id: int, title: str = ""
    ) -> SessionRecord:
        await self._companions.get(user_id, companion_id)  # 校验归属
        return await self._repo.create_session(user_id, companion_id, title.strip())

    async def list_sessions(self, user_id: str, companion_id: int) -> list[SessionRecord]:
        await self._companions.get(user_id, companion_id)
        return await self._repo.list_sessions(user_id, companion_id)

    async def get_session(self, user_id: str, session_id: int) -> SessionRecord:
        session = await self._repo.get_session(user_id, session_id)
        if session is None:
            raise NotFound("会话不存在")
        return session

    async def list_messages(
        self,
        user_id: str,
        session_id: int,
        *,
        before_seq: int | None = None,
        limit: int = 20,
    ) -> list[MessageRecord]:
        await self.get_session(user_id, session_id)
        return await self._repo.list_messages(
            user_id, session_id, before_seq=before_seq, limit=limit
        )

    async def delete_session(self, user_id: str, session_id: int) -> None:
        await self.get_session(user_id, session_id)
        await self._repo.delete_session(user_id, session_id)

    async def rename_session(self, user_id: str, session_id: int, title: str) -> SessionRecord:
        cleaned = (title or "").strip()
        if not cleaned:
            raise InvalidInput("会话标题不能为空")
        if len(cleaned) > 60:
            raise InvalidInput("会话标题最多 60 字")
        await self.get_session(user_id, session_id)
        updated = await self._repo.rename_session(user_id, session_id, cleaned)
        if updated is None:
            raise NotFound("会话不存在")
        return updated

    async def delete_message(self, user_id: str, message_id: int) -> None:
        if not await self._repo.delete_message(user_id, message_id):
            raise NotFound("消息不存在")

    async def latest_message(self, user_id: str, companion_id: int) -> MessageRecord | None:
        await self._companions.get(user_id, companion_id)
        return await self._repo.latest_for_companion(user_id, companion_id)

    async def open_session(self, user_id: str, session_id: int, request_id: str) -> MessageRecord:
        """她先开口：仅对空会话生成一次开场白，失败用模板兜底。"""
        session = await self.get_session(user_id, session_id)
        existing = await self._repo.list_messages(user_id, session_id, limit=1)
        if existing:
            return existing[0]
        companion = await self._companions.get(user_id, session.companion_id)
        now = datetime.now(SHANGHAI)
        prompt = companion.compiled_prompt + OPENERS_NOTE.format(time_hint=time_hint(now))
        messages = self._build_messages(prompt, []) + [
            Message(role=Role.USER, content="（现在由你先开口。）")
        ]
        collected = ""
        try:
            async for chunk in self._streamer.stream(
                TaskName.CHAT_MAIN,
                messages,
                context=CallContext(
                    user_id=user_id, request_id=request_id, task=TaskName.CHAT_MAIN
                ),
            ):
                if chunk.delta:
                    collected += chunk.delta
        except Exception:
            collected = ""
        text = collected.strip() or self._fallback_opener(companion)
        message = await self._repo.append_message(user_id, session.id, "assistant", text)
        await self._repo.touch_session(user_id, session.id, title=session.title or "初次见面")
        return message

    def _fallback_opener(self, companion: CompanionRecord) -> str:
        openers = companion.persona.example_openers or []
        if openers:
            return openers[0]
        return "我在呢，今天过得怎么样？"

    def _build_messages(self, system_prompt: str, history: list[MessageRecord]) -> list[Message]:
        messages = [Message(role=Role.SYSTEM, content=system_prompt)]
        for item in history:
            role = Role.ASSISTANT if item.role == "assistant" else Role.USER
            messages.append(Message(role=role, content=item.content))
        return messages

    async def _build_context(
        self,
        user_id: str,
        companion: CompanionRecord,
        session: SessionRecord,
        history: list[MessageRecord],
        query: str,
        request_id: str,
        *,
        crisis: bool = False,
        restricted: bool = False,
    ) -> tuple[str, list[MessageRecord], list[str]]:
        prompt = companion.compiled_prompt + SAFETY_NOTE
        if crisis:
            prompt += CRISIS_NOTE
        elif restricted:
            prompt += RESTRICTED_NOTE
        recalled: list[str] = []
        if self._memory is not None and companion.memory_enabled:
            try:
                memories = await self._memory.recall(user_id, companion.id, query, limit=6)
            except Exception:
                memories = []
            recalled = [item.content for item in memories[:2]]
            prompt += format_for_prompt(memories)

        plan = plan_history(
            history,
            system_tokens=estimate_tokens(prompt),
            budget_tokens=self._context_budget,
        )
        if plan.older:
            summary = await self._ensure_summary(user_id, session.id, plan.older, request_id)
            if summary:
                prompt += "\n\n# 此前对话摘要\n" + summary
        return prompt, plan.kept, recalled

    async def _ensure_summary(
        self,
        user_id: str,
        session_id: int,
        older: list[MessageRecord],
        request_id: str,
    ) -> str | None:
        if self._summaries is None or self._summarizer is None or not older:
            return None
        last_seq = older[-1].seq
        existing = await self._summaries.get(session_id)
        if existing is not None and existing.covered_seq >= last_seq:
            return existing.summary
        prompt = build_summary_prompt(
            transcript_of(older), existing.summary if existing is not None else None
        )
        result = await self._summarizer.complete(
            TaskName.SUMMARIZE,
            [
                Message(role=Role.SYSTEM, content="你是对话摘要助手，只输出摘要正文。"),
                Message(role=Role.USER, content=prompt),
            ],
            context=CallContext(user_id=user_id, request_id=request_id, task=TaskName.SUMMARIZE),
        )
        record = await self._summaries.upsert(session_id, clamp_summary(result.text), last_seq)
        return record.summary

    async def stream_reply(
        self,
        user_id: str,
        session_id: int,
        content: str,
        request_id: str,
        *,
        client_request_id: str | None = None,
    ) -> AsyncIterator[ChatEvent]:
        text = (content or "").strip()
        if not text:
            raise InvalidInput("消息不能为空")
        if len(text) > MAX_MESSAGE_CHARS:
            raise InvalidInput(f"单条消息最多 {MAX_MESSAGE_CHARS} 字")
        session = await self.get_session(user_id, session_id)
        companion = await self._companions.get(user_id, session.companion_id)
        if client_request_id:
            duplicated = await self._repo.find_by_request(user_id, session_id, client_request_id)
            if duplicated is not None:
                raise AppError(
                    code="DUPLICATE_REQUEST", message="这条消息已经发送过了", status_code=409
                )

        user_message = await self._repo.append_message(
            user_id, session_id, "user", text, client_request_id
        )
        yield ChatMeta(session_id=session_id, user_message_id=user_message.id)

        if self._quota is not None:
            await self._quota.consume(user_id)

        assessment = assess_input(text)
        if assessment.level != "normal" and self._safety is not None:
            try:
                await self._safety.record(
                    user_id, session_id, assessment.level, assessment.keywords
                )
            except Exception:
                pass  # 留痕失败不影响对话

        history = await self._repo.list_messages(user_id, session_id, limit=MAX_HISTORY_MESSAGES)
        system_prompt, kept_messages, recalled = await self._build_context(
            user_id,
            companion,
            session,
            history,
            text,
            request_id,
            crisis=assessment.is_crisis,
            restricted=assessment.is_restricted,
        )
        messages = self._build_messages(system_prompt, kept_messages)
        collected = ""
        usage_parts: list[Usage] = []
        model_key = ""
        try:
            async for chunk in self._streamer.stream(
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
            if collected:
                await self._repo.append_message(user_id, session_id, "assistant", collected)
                await self._repo.touch_session(user_id, session_id)
            elif self._quota is not None:
                # 一个字都没生成：返还次数，避免网络问题白扣
                await self._quota.refund(user_id)
            raise

        assistant = await self._repo.append_message(user_id, session_id, "assistant", collected)
        await self._repo.touch_session(
            user_id, session_id, title=text[:20] if not session.title else None
        )
        self._schedule_memory(user_id, companion, session_id, history, collected, request_id)
        yield ChatDone(
            assistant_message_id=assistant.id,
            model_key=model_key,
            usage=aggregate_usage(usage_parts),
            memories=recalled,
        )

    def _schedule_memory(
        self,
        user_id: str,
        companion: CompanionRecord,
        session_id: int,
        history: list[MessageRecord],
        collected: str,
        request_id: str,
    ) -> None:
        if self._memory is None or not companion.memory_enabled:
            return
        turns = [(item.role, item.content) for item in history[-4:]]
        if collected:
            turns.append(("assistant", collected))
        if not turns:
            return
        task = asyncio.create_task(
            self._memory.remember(user_id, companion.id, session_id, turns, request_id)
        )
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def regenerate(
        self, user_id: str, message_id: int, request_id: str
    ) -> AsyncIterator[ChatEvent]:
        """重新生成最后一条助手回复：原地替换内容，不新增用户消息。"""
        target = await self._repo.get_message(user_id, message_id)
        if target is None:
            raise NotFound("消息不存在")
        if target.role != "assistant":
            raise InvalidInput("只能重新生成伴侣的回复", code="REGENERATE_TARGET")
        session = await self.get_session(user_id, target.session_id)
        companion = await self._companions.get(user_id, session.companion_id)
        latest = await self._repo.list_messages(user_id, session.id, limit=1)
        if not latest or latest[0].id != target.id:
            raise AppError(
                code="REGENERATE_NOT_LAST",
                message="只能重新生成最后一条回复",
                status_code=409,
            )
        if self._quota is not None:
            await self._quota.consume(user_id)

        history = await self._repo.list_messages(
            user_id, session.id, before_seq=target.seq, limit=MAX_HISTORY_MESSAGES
        )
        last_user = next((item for item in reversed(history) if item.role == "user"), None)
        query = last_user.content if last_user is not None else ""
        assessment = assess_input(query)
        system_prompt, kept_messages, recalled = await self._build_context(
            user_id,
            companion,
            session,
            history,
            query,
            request_id,
            crisis=assessment.is_crisis,
            restricted=assessment.is_restricted,
        )
        messages = self._build_messages(system_prompt, kept_messages)
        yield ChatMeta(session_id=session.id, user_message_id=target.id)

        collected = ""
        usage_parts: list[Usage] = []
        model_key = ""
        try:
            async for chunk in self._streamer.stream(
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
            if not collected and self._quota is not None:
                await self._quota.refund(user_id)
            raise

        await self._repo.update_message(user_id, target.id, collected)
        yield ChatDone(
            assistant_message_id=target.id,
            model_key=model_key,
            usage=aggregate_usage(usage_parts),
            memories=recalled,
        )
