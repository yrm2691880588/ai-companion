"""P0-3 人设衍生：只复制人设，不复制会话/记忆/头像。"""

from decimal import Decimal

import pytest

from app.core.errors import AppError
from app.domain.chat import ChatService, InMemoryChatRepository
from app.domain.companions import (
    MAX_COMPANIONS,
    CompanionService,
    InMemoryCompanionRepository,
    LLMResult,
)
from app.domain.memory import InMemoryMemoryRepository
from app.domain.persona import Persona
from app.domain.usage import CallContext
from app.infra.llm.types import Usage

PERSONA = Persona.model_validate(
    {
        "name": "林夏",
        "identity": "心理学研究生",
        "gender": "女",
        "age": 24,
        "personality": ["温柔", "偶尔毒舌"],
        "speaking_style": "句子短，先共情再给建议。",
        "background": "在读心理学研究生，晚上在便利店兼职，见过很多深夜的人。",
        "tags": ["温柔", "学姐"],
        "relationship": "住在隔壁的学姐",
    }
)


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


async def build():
    companions = InMemoryCompanionRepository()
    service = CompanionService(companions, FakeLLM())
    source = await service.create("u1", PERSONA)
    return service, source


async def test_derive_creates_new_companion() -> None:
    service, source = await build()
    derived_persona = source.persona.model_copy(update={"name": "林夏·温柔版", "tags": ["温柔"]})
    created = await service.derive("u1", source.id, derived_persona)
    assert created.id != source.id
    assert created.name == "林夏·温柔版"
    assert created.derived_from == source.id


async def test_derive_does_not_change_source() -> None:
    service, source = await build()
    before = (source.name, source.current_version, source.persona.model_dump())
    await service.derive("u1", source.id, source.persona.model_copy(update={"name": "新版本"}))
    after = await service.get("u1", source.id)
    assert (after.name, after.current_version, after.persona.model_dump()) == before


async def test_derive_does_not_copy_sessions_or_memories() -> None:
    service, source = await build()
    chats = InMemoryChatRepository()
    chat_service = ChatService(chats, service, None)  # type: ignore[arg-type]
    await chat_service.create_session("u1", source.id)
    memories = InMemoryMemoryRepository()
    await memories.add(
        "u1",
        source.id,
        type="habit",
        content="每天刷题",
        confidence=0.9,
        quote=None,
        source_session_id=None,
        source_message_id=None,
    )
    created = await service.derive("u1", source.id, source.persona)
    assert await chats.list_sessions("u1", created.id) == []
    assert await memories.list("u1", created.id, limit=10) == []


async def test_derive_rejects_when_limit_reached() -> None:
    service, source = await build()
    for index in range(MAX_COMPANIONS - 1):
        await service.create("u1", PERSONA.model_copy(update={"name": f"伴侣{index}"}))
    with pytest.raises(AppError) as excinfo:
        await service.derive("u1", source.id, source.persona)
    assert excinfo.value.code == "COMPANION_LIMIT"


async def test_derive_requires_ownership() -> None:
    service, source = await build()
    from app.core.errors import NotFound

    with pytest.raises(NotFound):
        await service.derive("u2", source.id, source.persona)
