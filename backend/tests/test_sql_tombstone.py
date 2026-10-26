"""真库集成测试：墓碑消息在 SQL 仓储下不可读、不可改。

默认跳过；设置 AI_COMPANION_TEST_DATABASE_URL 后运行：
    $env:AI_COMPANION_TEST_DATABASE_URL='postgresql+asyncpg://app:app@localhost:5432/companion'
    pytest tests/test_sql_tombstone.py -v
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
import pytest_asyncio

from app.domain.chat import ChatService
from app.domain.companions import CompanionService, LLMResult
from app.domain.persona import Persona
from app.domain.usage import CallContext
from app.infra.chat_repo import SqlChatRepository
from app.infra.companion_repo import SqlCompanionRepository
from app.infra.db import build_engine, build_session_factory
from app.infra.llm.types import ChatChunk, Usage

DATABASE_URL = os.environ.get("AI_COMPANION_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="未配置真库测试连接")

PERSONA = Persona.model_validate(
    {
        "name": "墓碑测试",
        "identity": "测试角色",
        "gender": "不设定",
        "age": 25,
        "personality": ["安静", "可靠"],
        "speaking_style": "句子短，语气平稳。",
        "background": "仅用于自动化测试的临时角色，测试结束后会被清理。",
        "tags": ["测试"],
        "relationship": "测试关系",
    }
)


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


class FakeStreamer:
    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        yield ChatChunk(delta="收到。", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=5, completion_tokens=2))


@pytest_asyncio.fixture()
async def services():  # type: ignore[no-untyped-def]
    engine = build_engine(DATABASE_URL)
    session_factory = build_session_factory(engine)
    companions = SqlCompanionRepository(session_factory)
    chats = SqlChatRepository(session_factory)
    companion_service = CompanionService(companions, FakeLLM())
    chat_service = ChatService(chats, companion_service, FakeStreamer())
    user_id = f"pytest-tombstone-{os.getpid()}"
    companion = await companion_service.create(user_id, PERSONA)
    await chat_service.create_session(user_id, companion.id)
    try:
        yield user_id, companion.id, chat_service, chats
    finally:
        from sqlalchemy import text

        async with session_factory() as db:
            await db.execute(
                text("DELETE FROM companions WHERE user_id = :user"), {"user": user_id}
            )
            await db.commit()
        await engine.dispose()


@pytest.mark.asyncio
async def test_deleted_message_is_hidden_and_immutable(services) -> None:  # type: ignore[no-untyped-def]
    user_id, _companion_id, chat_service, chats = services
    session = (await chat_service.list_sessions(user_id, _companion_id))[0]
    assert session is not None
    [event async for event in chat_service.stream_reply(user_id, session.id, "你好", "r1")]
    assistant = (await chat_service.list_messages(user_id, session.id))[-1]

    await chat_service.delete_message(user_id, assistant.id)

    visible = await chat_service.list_messages(user_id, session.id)
    assert all(item.id != assistant.id for item in visible)
    assert await chats.get_message(user_id, assistant.id) is None
    assert await chats.update_message(user_id, assistant.id, "被改回来") is None
