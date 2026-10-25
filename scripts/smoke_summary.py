"""上下文压缩冒烟：长历史 → 摘要 → 真实回复仍然记得关键信息。

运行（仓库根目录）：
    backend/.venv/Scripts/python.exe scripts/smoke_summary.py
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
from app.infra.chat_repo import SqlChatRepository  # noqa: E402
from app.infra.companion_repo import SqlCompanionRepository  # noqa: E402
from app.infra.db import build_engine, build_session_factory  # noqa: E402
from app.infra.llm.client import RouterLLMClient  # noqa: E402
from app.infra.llm.gateway import LLMGateway  # noqa: E402
from app.infra.llm.registry import ModelRegistry  # noqa: E402
from app.infra.llm.router import ModelRouter  # noqa: E402
from app.infra.memory_repo import SqlMemoryRepository  # noqa: E402
from app.infra.summary_repo import SqlSummaryRepository  # noqa: E402
from app.infra.template_repo import SqlTemplateRepository  # noqa: E402
from app.infra.usage_repo import SqlUsageRepository  # noqa: E402

USER_ID = "smoke-summary"
BUDGET = 600  # 故意压小，强制触发摘要

PLAN = [
    "我下周三要考数据分析师，最近在复习 SQL，尤其是窗口函数和索引优化。",
    "今天刷了三十道题，错了很多窗口函数的题，感觉对 partition by 的理解还不够。",
    "我发现自己一遇到排名题就慌，脑子会空白，明明平时练习的时候是会做的。",
    "晚上在图书馆待到十点，效率一般，中间刷了两次手机，有点自责。",
    "室友总在打游戏，声音有点吵，我不好意思说，只能戴耳机。",
    "我决定明天早上先做两套真题，下午再复盘错题，晚上整理业务指标。",
    "如果这次没过，我打算十二月再考一次，不想因为一次失败就放弃。",
    "我妈问我进度，我有点压力，她其实只是关心，但我不想让她失望。",
    "其实我最想去的公司是做电商的，听说他们的面试会考业务指标拆解。",
    "面试官说会考业务指标拆解，比如 GMV 下降怎么定位，我还没想清楚。",
    "我准备把常用的指标定义背下来：MAU、GMV、转化率、客单价、复购率。",
    "今天有点学不进去，但还是坐下写了会题，写了五道就困了，先睡了。",
]


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
    chat_repo = SqlChatRepository(session_factory)
    summary_repo = SqlSummaryRepository(session_factory)
    chat = ChatService(
        chat_repo,
        companion_service,
        router,
        memory=None,
        summaries=summary_repo,
        summarizer=client,
        context_budget_tokens=BUDGET,
    )

    companion = await companion_service.create_from_template(USER_ID, "study_buddy")
    session = await chat.create_session(USER_ID, companion.id, "备考记录")
    print(f"[1] 伴侣 {companion.name}，会话 {session.id}，历史预算 {BUDGET} tokens")

    print("\n[2] 预置 12 轮历史（模拟长对话）")
    for index, line in enumerate(PLAN):
        role = "user" if index % 2 == 0 else "assistant"
        await chat_repo.append_message(USER_ID, session.id, role, line)
    print(f"  已写入 {len(PLAN)} 条消息，约 {sum(len(item) for item in PLAN)} 字")

    print("\n[3] 发一句新消息（会触发摘要）")
    reply = ""
    done: ChatDone | None = None
    async for event in chat.stream_reply(
        USER_ID, session.id, "我有点慌，明天就要考试了，你还记得我的安排吗？", str(uuid4())
    ):
        if isinstance(event, ChatDelta):
            reply += event.text
        elif isinstance(event, ChatDone):
            done = event
    print(f"  伴侣：{reply}")
    if done:
        print(f"  模型 {done.model_key} | in {done.usage.input_tokens} / out {done.usage.completion_tokens}")

    record = await summary_repo.get(session.id)
    print("\n[4] 摘要结果")
    if record is None:
        print("  未生成摘要（预算可能仍然够用）")
    else:
        print(f"  覆盖到 seq={record.covered_seq}")
        print(f"  摘要：{record.summary}")

    print("\n[5] 消息与摘要核对")
    messages = await chat.list_messages(USER_ID, session.id, limit=100)
    print(f"  会话共 {len(messages)} 条消息；摘要覆盖前 {record.covered_seq if record else 0} 条")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
