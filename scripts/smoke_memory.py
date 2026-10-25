"""记忆链路冒烟：真实对话 → 自动抽取 → 跨会话召回。

运行（仓库根目录）：
    backend/.venv/Scripts/python.exe scripts/smoke_memory.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.domain.chat import ChatDelta, ChatDone, ChatService  # noqa: E402
from app.domain.companions import CompanionService  # noqa: E402
from app.domain.memory import MemoryService, format_for_prompt  # noqa: E402
from app.infra.chat_repo import SqlChatRepository  # noqa: E402
from app.infra.companion_repo import SqlCompanionRepository  # noqa: E402
from app.infra.db import build_engine, build_session_factory  # noqa: E402
from app.infra.llm.client import RouterLLMClient  # noqa: E402
from app.infra.llm.gateway import LLMGateway  # noqa: E402
from app.infra.llm.registry import ModelRegistry  # noqa: E402
from app.infra.llm.router import ModelRouter  # noqa: E402
from app.infra.memory_repo import SqlMemoryRepository  # noqa: E402
from app.infra.template_repo import SqlTemplateRepository  # noqa: E402
from app.infra.usage_repo import SqlUsageRepository  # noqa: E402

USER_ID = "smoke-memory"


async def say(chat: ChatService, session_id: int, text: str) -> str:
    reply = ""
    done: ChatDone | None = None
    async for event in chat.stream_reply(USER_ID, session_id, text, str(uuid4())):
        if isinstance(event, ChatDelta):
            reply += event.text
        elif isinstance(event, ChatDone):
            done = event
    print(f"  用户：{text}")
    print(f"  伴侣：{reply}")
    if done:
        print(f"  （{done.model_key} | in {done.usage.input_tokens} / out {done.usage.completion_tokens}）")
    return reply


async def main() -> int:
    settings = get_settings()
    registry = ModelRegistry.from_presets(keys=settings.provider_keys())
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    usage_repo = SqlUsageRepository(session_factory)
    router = ModelRouter(
        registry,
        LLMGateway(timeout_seconds=120),
        turn_cost_cap_cny=settings.turn_cost_cap_cny,
        hit_ratio=settings.default_hit_ratio,
        recorder=usage_repo,
    )
    client = RouterLLMClient(router, registry)
    companion_service = CompanionService(
        SqlCompanionRepository(session_factory), client, SqlTemplateRepository(session_factory)
    )
    memory_service = MemoryService(SqlMemoryRepository(session_factory), client)
    chat_service = ChatService(
        SqlChatRepository(session_factory), companion_service, router, memory_service
    )

    companion = await companion_service.create_from_template(USER_ID, "interview_coach")
    print(f"[1] 伴侣：{companion.name}（{companion.persona.identity}），id={companion.id}")

    print("\n[2] 第一段对话（会自动抽取记忆）")
    session1 = await chat_service.create_session(USER_ID, companion.id, "面试准备")
    await say(chat_service, session1.id, "我下周五要去字节面试，最近每天刷两道算法题。")
    await say(chat_service, session1.id, "我有点怕被问项目细节。")
    await asyncio.sleep(2)  # 等后台抽取任务完成

    memories = await memory_service.list(USER_ID, companion.id)
    if not memories:
        print("  后台未完成，手动触发一次抽取")
        messages = await chat_service.list_messages(USER_ID, session1.id, limit=6)
        memories = await memory_service.extract(
            USER_ID,
            companion.id,
            session1.id,
            [(item.role, item.content) for item in messages],
            str(uuid4()),
        )
    print(f"\n[3] 已沉淀 {len(memories)} 条记忆")
    for item in memories:
        print(f"  - [{item.type}] {item.content}（置信度 {item.confidence}）")

    print("\n[4] 跨会话召回（新会话里问一句）")
    recalled = await memory_service.recall(USER_ID, companion.id, "我明天面试有点紧张")
    print(format_for_prompt(recalled) or "  （没有召回）")

    session2 = await chat_service.create_session(USER_ID, companion.id, "面试前夜")
    await say(chat_service, session2.id, "我明天面试，有点紧张。")

    print("\n[5] 落库核对")
    from sqlalchemy import text

    async with session_factory() as session:
        rows = (
            await session.execute(
                text("SELECT type, content FROM memories WHERE user_id=:uid ORDER BY id"),
                {"uid": USER_ID},
            )
        ).all()
    for row in rows:
        print(f"  DB: [{row.type}] {row.content}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
