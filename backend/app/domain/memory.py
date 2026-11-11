"""长期记忆：抽取、去重、召回与提示词格式化。

V1 口径：
- 只抽「用户明确说过的、关于用户本人的事实」；
- 敏感信息（住址/证件/健康/财务）默认不抽，除非原话说“记住这个”；
- 同类型 + 同内容视为重复，不重复写入；
- 召回先用「关键词重合 + 类型权重」，向量召回在 embedding 服务就绪后接上。
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from app.core.errors import InvalidInput, NotFound
from app.domain.companions import LLMClient
from app.domain.usage import CallContext
from app.infra.llm.types import Message, Role, TaskName

MAX_ITEM_CHARS = 120
MAX_ITEMS_PER_TURN = 5
MIN_CONFIDENCE = 0.6


class MemoryType(StrEnum):
    PREFERENCE = "preference"
    EXPERIENCE = "experience"
    HABIT = "habit"
    PROMISE = "promise"
    RELATIONSHIP = "relationship"
    BOUNDARY = "boundary"


TYPE_LABELS = {
    MemoryType.PREFERENCE: "喜好",
    MemoryType.EXPERIENCE: "经历",
    MemoryType.HABIT: "习惯",
    MemoryType.PROMISE: "约定",
    MemoryType.RELATIONSHIP: "关系",
    MemoryType.BOUNDARY: "边界",
}

TYPE_WEIGHTS = {
    MemoryType.PROMISE: 4.0,
    MemoryType.EXPERIENCE: 3.0,
    MemoryType.BOUNDARY: 3.0,
    MemoryType.RELATIONSHIP: 2.0,
    MemoryType.PREFERENCE: 2.0,
    MemoryType.HABIT: 1.5,
}

SENSITIVE_KEYWORDS = (
    "身份证",
    "银行卡",
    "密码",
    "住址",
    "住在",
    "家住",
    "病史",
    "病历",
    "医院",
    "工资",
    "存款",
    "手机号",
    "开房",
    "裸照",
)


@dataclass(slots=True)
class MemoryRecord:
    id: int
    user_id: str
    companion_id: int
    type: str
    content: str
    confidence: float = 0.7
    status: str = "active"
    source_session_id: int | None = None
    source_message_id: int | None = None
    quote: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime | None = None
    ulid: str = ""


class MemoryRepository(Protocol):
    async def add(
        self,
        user_id: str,
        companion_id: int,
        *,
        type: str,
        content: str,
        confidence: float,
        quote: str | None,
        source_session_id: int | None,
        source_message_id: int | None,
    ) -> MemoryRecord: ...

    async def list(
        self,
        user_id: str,
        companion_id: int,
        *,
        type: str | None = None,
        status: str = "active",
        limit: int = 100,
    ) -> list[MemoryRecord]: ...

    async def get(self, user_id: str, memory_id: int) -> MemoryRecord | None: ...

    async def soft_delete(self, user_id: str, memory_id: int) -> bool: ...

    async def find_duplicate(
        self, user_id: str, companion_id: int, type: str, content: str
    ) -> MemoryRecord | None: ...

    async def mark_used(self, memory_ids: Sequence[int]) -> None: ...


class InMemoryMemoryRepository:
    def __init__(self) -> None:
        self.items: dict[int, MemoryRecord] = {}
        self._next_id = 1

    async def add(
        self,
        user_id: str,
        companion_id: int,
        *,
        type: str,
        content: str,
        confidence: float,
        quote: str | None,
        source_session_id: int | None,
        source_message_id: int | None,
    ) -> MemoryRecord:
        record = MemoryRecord(
            id=self._next_id,
            user_id=user_id,
            companion_id=companion_id,
            type=type,
            content=content,
            confidence=confidence,
            quote=quote,
            source_session_id=source_session_id,
            source_message_id=source_message_id,
        )
        self.items[record.id] = record
        self._next_id += 1
        return record

    async def list(
        self,
        user_id: str,
        companion_id: int,
        *,
        type: str | None = None,
        status: str = "active",
        limit: int = 100,
    ) -> list[MemoryRecord]:
        items = [
            item
            for item in self.items.values()
            if item.user_id == user_id
            and item.companion_id == companion_id
            and item.status == status
            and (type is None or item.type == type)
        ]
        return sorted(items, key=lambda item: item.created_at, reverse=True)[:limit]

    async def get(self, user_id: str, memory_id: int) -> MemoryRecord | None:
        item = self.items.get(memory_id)
        return item if item is not None and item.user_id == user_id else None

    async def soft_delete(self, user_id: str, memory_id: int) -> bool:
        item = await self.get(user_id, memory_id)
        if item is None:
            return False
        item.status = "deleted"
        return True

    async def find_duplicate(
        self, user_id: str, companion_id: int, type: str, content: str
    ) -> MemoryRecord | None:
        normalized = normalize_content(content)
        for item in await self.list(user_id, companion_id):
            if item.type == type and normalize_content(item.content) == normalized:
                return item
        return None

    async def mark_used(self, memory_ids: Sequence[int]) -> None:
        now = datetime.now(UTC)
        for memory_id in memory_ids:
            item = self.items.get(memory_id)
            if item is not None:
                item.last_used_at = now


def normalize_content(text: str) -> str:
    return re.sub(r"[\s，。！？、,.!?；;：:“”\"'（）()]", "", text).lower()


def is_sensitive(content: str, quote: str | None) -> bool:
    text = f"{content}{quote or ''}"
    if "记住" in text:
        return False
    return any(keyword in text for keyword in SENSITIVE_KEYWORDS)


def _bigrams(text: str) -> set[str]:
    cleaned = normalize_content(text)
    return {cleaned[index : index + 2] for index in range(len(cleaned) - 1)}


def overlap_ratio(query: str, content: str) -> float:
    query_grams = _bigrams(query)
    content_grams = _bigrams(content)
    if not query_grams or not content_grams:
        return 0.0
    return len(query_grams & content_grams) / len(query_grams)


_EXTRACT_SYSTEM = """你从对话里抽取值得长期记住的、关于用户本人的事实。
规则：
1. 只抽用户明确说过的内容，不要推测，不要抽提问或对 AI 的要求。
2. 类型：preference(喜好)、experience(经历)、habit(习惯)、
   promise(约定/计划)、relationship(关系)、boundary(边界/雷区)。
3. 敏感信息（住址、证件、健康、财务）除非用户说“记住这个”，否则不要抽。
4. 一条不超过 60 字，必须是完整的一句事实。
5. 只输出 JSON：{"items":[{"type":"...","content":"...","confidence":0.8,"quote":"对话里的原句"}]}
6. 最多 5 条；没有可记的就输出 {"items":[]}。"""


def _transcript(turns: Sequence[tuple[str, str]]) -> str:
    lines = []
    for role, content in turns:
        label = "用户" if role == "user" else "伴侣"
        lines.append(f"{label}：{content}")
    return "\n".join(lines)


def parse_items(text: str) -> list[dict[str, object]]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise InvalidInput("记忆抽取没有返回 JSON", code="MEMORY_JSON_INVALID") from None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise InvalidInput("记忆抽取没有返回 JSON", code="MEMORY_JSON_INVALID") from exc
    if not isinstance(data, dict):
        raise InvalidInput("记忆抽取结果必须是对象", code="MEMORY_JSON_INVALID")
    items = data.get("items", [])
    if not isinstance(items, list):
        raise InvalidInput("记忆抽取结果 items 必须是数组", code="MEMORY_JSON_INVALID")
    return [item for item in items if isinstance(item, dict)]


class MemoryPort(Protocol):
    async def recall(
        self, user_id: str, companion_id: int, query: str, *, limit: int = 6
    ) -> list[MemoryRecord]: ...

    async def remember(
        self,
        user_id: str,
        companion_id: int,
        session_id: int,
        turns: Sequence[tuple[str, str]],
        request_id: str,
    ) -> list[MemoryRecord]: ...


class MemoryService:
    def __init__(self, repo: MemoryRepository, llm: LLMClient) -> None:
        self._repo = repo
        self._llm = llm

    async def extract(
        self,
        user_id: str,
        companion_id: int,
        session_id: int | None,
        turns: Sequence[tuple[str, str]],
        request_id: str,
    ) -> list[MemoryRecord]:
        if not turns:
            return []
        context = CallContext(user_id=user_id, request_id=request_id, task=TaskName.MEMORY_EXTRACT)
        messages = [
            Message(role=Role.SYSTEM, content=_EXTRACT_SYSTEM),
            Message(role=Role.USER, content=_transcript(turns)),
        ]
        result = await self._llm.complete(TaskName.MEMORY_EXTRACT, messages, context=context)
        try:
            raw_items = parse_items(result.text)
        except InvalidInput:
            return []

        created: list[MemoryRecord] = []
        for raw in raw_items:
            if len(created) >= MAX_ITEMS_PER_TURN:
                break
            memory_type = str(raw.get("type", "")).strip()
            content = str(raw.get("content", "")).strip()
            quote = raw.get("quote")
            quote_text = str(quote).strip() if quote is not None else None
            if memory_type not in {item.value for item in MemoryType}:
                continue
            if not (4 <= len(content) <= MAX_ITEM_CHARS):
                continue
            confidence = float(raw.get("confidence", 0.7) or 0.7)
            if confidence < MIN_CONFIDENCE:
                continue
            if is_sensitive(content, quote_text):
                continue
            if await self._repo.find_duplicate(user_id, companion_id, memory_type, content):
                continue
            # 近似重复：同类型下与已有记忆高度重合就跳过（例如「明天要开会」与「明天有个会」）
            existing = await self._repo.list(user_id, companion_id, type=memory_type, limit=200)
            if any(
                max(
                    overlap_ratio(content, item.content),
                    overlap_ratio(item.content, content),
                )
                >= 0.75
                for item in existing
            ):
                continue
            created.append(
                await self._repo.add(
                    user_id,
                    companion_id,
                    type=memory_type,
                    content=content,
                    confidence=min(confidence, 1.0),
                    quote=quote_text,
                    source_session_id=session_id,
                    source_message_id=None,
                )
            )
        return created

    async def list(
        self,
        user_id: str,
        companion_id: int,
        *,
        type: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        if type is not None and type not in {item.value for item in MemoryType}:
            raise InvalidInput("未知的记忆类型", code="UNKNOWN_MEMORY_TYPE")
        return await self._repo.list(user_id, companion_id, type=type, limit=limit)

    async def delete(self, user_id: str, memory_id: int) -> None:
        memory = await self._repo.get(user_id, memory_id)
        if memory is None:
            raise NotFound("记忆不存在")
        if not await self._repo.soft_delete(user_id, memory_id):
            raise NotFound("记忆不存在")

    async def recall(
        self, user_id: str, companion_id: int, query: str, *, limit: int = 6
    ) -> list[MemoryRecord]:
        candidates = await self._repo.list(user_id, companion_id, limit=200)
        scored: list[tuple[float, MemoryRecord]] = []
        now = datetime.now(UTC)
        for item in candidates:
            weight = TYPE_WEIGHTS.get(MemoryType(item.type), 1.0)
            score = weight + overlap_ratio(query, item.content) * 5
            if item.last_used_at and now - item.last_used_at < timedelta(hours=24):
                score -= 1.0  # 24 小时内提过的降低权重，避免反复念同一件事
            if score >= 2.0:
                scored.append((score, item))
        scored.sort(key=lambda pair: (pair[0], pair[1].created_at), reverse=True)
        selected = [item for _, item in scored[:limit]]
        if selected:
            await self._repo.mark_used([item.id for item in selected])
        return selected

    async def remember(
        self,
        user_id: str,
        companion_id: int,
        session_id: int,
        turns: Sequence[tuple[str, str]],
        request_id: str,
    ) -> list[MemoryRecord]:
        return await self.extract(user_id, companion_id, session_id, turns, request_id)


def format_for_prompt(memories: Sequence[MemoryRecord]) -> str:
    if not memories:
        return ""
    lines = ["", "# 你记得的事（自然带出，不要像念清单）"]
    for item in memories:
        label = TYPE_LABELS.get(MemoryType(item.type), item.type)
        lines.append(f"- [{label}] {item.content}")
    return "\n".join(lines)


__all__ = [
    "InMemoryMemoryRepository",
    "MemoryPort",
    "MemoryRecord",
    "MemoryRepository",
    "MemoryService",
    "MemoryType",
    "TYPE_LABELS",
    "format_for_prompt",
    "is_sensitive",
    "normalize_content",
    "overlap_ratio",
    "parse_items",
]
