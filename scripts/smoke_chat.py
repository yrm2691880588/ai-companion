"""对话链路冒烟：真实 DeepSeek 流式回复 + 人设注入 + 历史承接 + 落库。

运行（仓库根目录）：
    backend/.venv/Scripts/python.exe scripts/smoke_chat.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.domain.chat import ChatDelta, ChatDone, ChatMeta, ChatService  # noqa: E402
from app.domain.companions import CompanionService  # noqa: E402
from app.infra.chat_repo import SqlChatRepository  # noqa: E402
from app.infra.companion_repo import SqlCompanionRepository  # noqa: E402
from app.infra.db import build_engine, build_session_factory  # noqa: E402
from app.infra.llm.client import RouterLLMClient  # noqa: E402
from app.infra.llm.gateway import LLMGateway  # noqa: E402
from app.infra.llm.registry import ModelRegistry  # noqa: E402
from app.infra.llm.router import ModelRouter  # noqa: E402
from app.infra.template_repo import SqlTemplateRepository  # noqa: E402
from app.infra.usage_repo import SqlUsageRepository  # noqa: E402

USER_ID = "smoke-chat"


async def main() -> int:
    settings = get_settings()
    registry = ModelRegistry.from_presets(keys=settings.provider_keys())
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    usage_repo = SqlUsageRepository(session_factory)
    companion_repo = SqlCompanionRepository(session_factory)
    template_repo = SqlTemplateRepository(session_factory)
    chat_repo = SqlChatRepository(session_factory)
    router = ModelRouter(
        registry,
        LLMGateway(timeout_seconds=120),
        turn_cost_cap_cny=settings.turn_cost_cap_cny,
        hit_ratio=settings.default_hit_ratio,
        recorder=usage_repo,
    )
    companion_service = CompanionService(
        companion_repo, RouterLLMClient(router, registry), template_repo
    )
    chat_service = ChatService(chat_repo, companion_service, router)

    print("[1] 从模板创建伴侣")
    companion = await companion_service.create_from_template(USER_ID, "warm_senior")
    print(f"  id={companion.id} 名称={companion.name} 人设版本={companion.current_version}")

    print("\n[2] 新建会话")
    session = await chat_service.create_session(USER_ID, companion.id, "第一次聊天")
    print(f"  会话 id={session.id} 标题={session.title}")

    turns = ["今天被领导当众否了，有点难受。", "你觉得我明天该怎么跟他说？"]
    for index, text in enumerate(turns, start=1):
        print(f"\n[3.{index}] 用户：{text}")
        reply = ""
        done: ChatDone | None = None
        async for event in chat_service.stream_reply(
            USER_ID, session.id, text, str(uuid4())
        ):
            if isinstance(event, ChatDelta):
                reply += event.text
            elif isinstance(event, ChatDone):
                done = event
            elif isinstance(event, ChatMeta):
                print(f"  用户消息 id={event.user_message_id}")
        print(f"  {companion.name}：{reply}")
        if done:
            print(
                f"  模型 {done.model_key} | 输入 {done.usage.input_tokens} tokens"
                f"（命中 {done.usage.cache_hit_tokens}）| 输出 {done.usage.completion_tokens} tokens"
            )

    print("\n[4] 落库核对")
    messages = await chat_service.list_messages(USER_ID, session.id, limit=20)
    for item in messages:
        print(f"  seq={item.seq} {item.role}: {item.content[:40]}")
    summary = await usage_repo.summary(USER_ID, days=1)
    print(
        f"\n本日调用 {summary.totals.calls} 次 | 输入 {summary.totals.input_tokens} tokens | "
        f"成本 ≈ ¥{summary.totals.cost_cny:.6f}"
    )
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
