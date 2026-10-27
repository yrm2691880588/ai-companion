"""为 CI 页面验收播种最小数据。

页面验收脚本要求：
- 首页至少有 1 个伴侣卡片；
- 能读取伴侣、进入人设页、调用导出与埋点接口。

本脚本只创建 1 个伴侣与 1 个会话，不调用任何外部模型，可重复执行。
用法（在 CI 中由 frontend-ci.yml 调用）：
    python scripts/seed_ci_data.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.core.ids import new_ulid  # noqa: E402
from app.domain.persona import Persona, compile_prompt  # noqa: E402
from app.infra.companion_repo import SqlCompanionRepository  # noqa: E402
from app.infra.db import build_engine, build_session_factory  # noqa: E402

PERSONA = {
    "name": "验收角色",
    "identity": "书店店员",
    "gender": "女",
    "age": 26,
    "personality": ["温和", "爱看书"],
    "speaking_style": "句子短，语气平稳，喜欢用具体的书名举例。",
    "background": "在城南旧书店工作，每天整理书架，午休时在窗边看小说。",
    "tags": ["书店", "安静"],
    "relationship": "常去的那家书店的店员",
    "example_openers": ["又来啦，今天想找什么书？"],
}


async def main() -> int:
    settings = get_settings()
    user_id = settings.local_user_id if settings.local_mode else settings.debug_user_id
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    try:
        repo = SqlCompanionRepository(session_factory)
        existing = await repo.list(user_id)
        if existing:
            print(f"已有 {len(existing)} 个伴侣，跳过播种")
            return 0

        persona = Persona.model_validate(PERSONA)
        record = await repo.create(
            user_id=user_id,
            name=persona.name,
            persona=persona,
            compiled_prompt=compile_prompt(persona),
            derived_from=None,
        )
        print(f"已创建验收伴侣 id={record.id} ulid={record.ulid or new_ulid()}")
    finally:
        await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
