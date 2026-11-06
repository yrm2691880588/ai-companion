"""为页面验收准备稳定的测试伴侣。

为什么需要：多个前端验收脚本硬编码了 `companions/19`（苏小糖·测试版）。
批量删除功能上线后，这个伴侣可能被用户或测试自己删掉，导致验收全线失败。
本脚本负责把它补回来，并设好音色——幂等，可重复执行。

用法：
    python scripts/seed_test_companion.py
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.ids import new_ulid  # noqa: E402
from app.infra.db import build_engine, build_session_factory  # noqa: E402
from app.models.companions import Companion, CompanionPersona  # noqa: E402

# 验收脚本依赖的名字与音色
NAME = "苏小糖·测试版"
VOICE_ID = "zh_female_vv_uranus_bigtts"

PERSONA = {
    "name": "苏小糖",
    "identity": "甜品学徒",
    "gender": "女",
    "age": 19,
    "personality": ["粘人", "爱撒娇", "嘴甜"],
    "speaking_style": "句子短，爱用语气词，喜欢撒娇。",
    "background": "在老街的甜品店当学徒，每天和奶油糖霜打交道。",
    "tags": ["甜妹", "粘人精"],
    "relationship": "你的小女友",
}
COMPILED = (
    "# 你是谁\n你是苏小糖，女，19 岁，甜品学徒。\n"
    "# 关系\n你的小女友。\n"
    "# 性格\n粘人、爱撒娇、嘴甜。\n"
    "# 说话方式\n句子短，爱用语气词。\n"
)


async def main() -> int:
    settings = get_settings()
    # 用户标识以配置为准，不要硬编码——写错会创建出「看不见」的伴侣
    local_user = settings.local_user_id
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    try:
        async with factory() as session:
            existing = (
                await session.execute(
                    select(Companion).where(
                        Companion.user_id == local_user,
                        Companion.name == NAME,
                        Companion.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()

            if existing is not None:
                if existing.voice_id != VOICE_ID:
                    existing.voice_id = VOICE_ID
                    await session.commit()
                    print(f"已存在 id={existing.id}，补设音色")
                else:
                    print(f"已存在 id={existing.id}，无需改动")
                print(f"TEST_COMPANION_ID={existing.id}")
                return 0

            companion = Companion(
                user_id=local_user,
                name=NAME,
                current_version=1,
                memory_enabled=True,
                voice_id=VOICE_ID,
                ulid=new_ulid(),
                origin_device_id="local",
            )
            session.add(companion)
            await session.flush()
            session.add(
                CompanionPersona(
                    companion_id=companion.id,
                    version=1,
                    persona=PERSONA,
                    compiled_prompt=COMPILED,
                    ulid=new_ulid(),
                    origin_device_id="local",
                )
            )
            await session.commit()
            print(f"已创建 id={companion.id}")
            print(f"TEST_COMPANION_ID={companion.id}")
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
