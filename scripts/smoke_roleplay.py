"""演练冒烟：真实 DeepSeek 扮演面试官 → 用户回答 → 生成复盘。

运行（仓库根目录）：
    backend/.venv/Scripts/python.exe scripts/smoke_roleplay.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.domain.chat import ChatDelta, ChatDone, ChatMeta  # noqa: E402
from app.domain.companions import CompanionService  # noqa: E402
from app.domain.roleplay import SCENARIOS, RoleplayService  # noqa: E402
from app.infra.chat_repo import SqlChatRepository  # noqa: E402
from app.infra.companion_repo import SqlCompanionRepository  # noqa: E402
from app.infra.db import build_engine, build_session_factory  # noqa: E402
from app.infra.llm.client import RouterLLMClient  # noqa: E402
from app.infra.llm.gateway import LLMGateway  # noqa: E402
from app.infra.llm.registry import ModelRegistry  # noqa: E402
from app.infra.llm.router import ModelRouter  # noqa: E402
from app.infra.roleplay_repo import SqlRunRepository, SqlScenarioRepository  # noqa: E402
from app.infra.template_repo import SqlTemplateRepository  # noqa: E402
from app.infra.usage_repo import SqlUsageRepository  # noqa: E402

USER_ID = "smoke-roleplay"


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
    scenario_repo = SqlScenarioRepository(session_factory)
    await scenario_repo.sync(SCENARIOS)
    roleplay = RoleplayService(
        scenario_repo,
        SqlRunRepository(session_factory),
        SqlChatRepository(session_factory),
        companion_service,
        router,
        client,
    )

    companion = await companion_service.create_from_template(USER_ID, "interview_coach")
    run, session, opening = await roleplay.start(USER_ID, companion.id, "interview_screen")
    print(f"[1] 场景：技术面试模拟，run={run.id}，session={session.id}，上限 {run.max_turns} 轮")
    print(f"  面试官：{opening.content}")

    turns = [
        "你好，我叫小林，做了三年后台开发，主要做订单系统。",
        "我负责过一个压测优化项目，把接口 P99 从 800ms 降到 200ms。",
    ]
    for index, text in enumerate(turns, start=1):
        print(f"\n[2.{index}] 用户：{text}")
        reply = ""
        done: ChatDone | None = None
        async for event in roleplay.stream_turn(USER_ID, run.id, text, str(uuid4())):
            if isinstance(event, ChatDelta):
                reply += event.text
            elif isinstance(event, ChatDone):
                done = event
            elif isinstance(event, ChatMeta):
                pass
        print(f"  面试官：{reply}")
        if done:
            print(f"  （{done.model_key} | in {done.usage.input_tokens} / out {done.usage.completion_tokens}）")

    print("\n[3] 生成复盘（会跳出角色给建议）")
    finished = await roleplay.finish(USER_ID, run.id, str(uuid4()))
    review = finished.review or {}
    print(f"  状态：{finished.status}，已进行 {finished.turns_played} 轮")
    print(f"  总评：{review.get('summary')}")
    print(f"  评分：{review.get('scores')}")
    print(f"  亮点：{review.get('highlights')}")
    print(f"  改进：{review.get('improvements')}")
    print(f"  示范句：{review.get('sample_lines')}")

    print("\n[4] 数据核对")
    from sqlalchemy import text

    async with session_factory() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT id, status, turns_played, (review IS NOT NULL) AS has_review "
                    "FROM roleplay_runs WHERE user_id=:uid ORDER BY id DESC LIMIT 3"
                ),
                {"uid": USER_ID},
            )
        ).all()
    for row in rows:
        print(f"  DB: run={row.id} status={row.status} turns={row.turns_played} review={row.has_review}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
