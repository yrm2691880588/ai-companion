"""人设生成冒烟：一句描述 → DeepSeek 生成人设 → 落库 → 改一维 → 单维重写。

运行（仓库根目录）：
    backend/.venv/Scripts/python.exe scripts/smoke_persona.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.domain.companions import CompanionService  # noqa: E402
from app.domain.persona import prompt_tokens  # noqa: E402
from app.infra.companion_repo import SqlCompanionRepository  # noqa: E402
from app.infra.db import build_engine, build_session_factory  # noqa: E402
from app.infra.llm.client import RouterLLMClient  # noqa: E402
from app.infra.llm.gateway import LLMGateway  # noqa: E402
from app.infra.llm.registry import ModelRegistry  # noqa: E402
from app.infra.llm.router import ModelRouter  # noqa: E402
from app.infra.usage_repo import SqlUsageRepository  # noqa: E402

USER_ID = "smoke-persona"
DESCRIPTION = "想要一个温柔但偶尔毒舌的心理学学姐，比我大两岁，晚上常熬夜"


def print_persona(persona) -> None:  # type: ignore[no-untyped-def]
    print(f"  名字: {persona.name} | {persona.gender} | {persona.age} 岁 | {persona.identity}")
    print(f"  性格: {'、'.join(persona.personality)}")
    print(f"  说话风格: {persona.speaking_style}")
    print(f"  背景: {persona.background[:120]}...")
    print(f"  标签: {'、'.join(persona.tags)} | 关系: {persona.relationship}")
    print(f"  开场白: {persona.example_openers[:2]}")


async def main() -> int:
    settings = get_settings()
    registry = ModelRegistry.from_presets(keys=settings.provider_keys())
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    usage_repo = SqlUsageRepository(session_factory)
    companion_repo = SqlCompanionRepository(session_factory)
    router = ModelRouter(
        registry,
        LLMGateway(timeout_seconds=120),
        turn_cost_cap_cny=settings.turn_cost_cap_cny,
        hit_ratio=settings.default_hit_ratio,
        recorder=usage_repo,
    )
    service = CompanionService(companion_repo, RouterLLMClient(router, registry))

    print("[1] 一句话生成人设")
    print(f"  输入: {DESCRIPTION}")
    persona, result = await service.generate_persona(USER_ID, DESCRIPTION, str(uuid4()))
    print_persona(persona)
    print(f"  模型: {result.model_key} | 成本 ≈ ¥{result.cost_cny:.6f}")
    print(f"  编译后提示词约 {prompt_tokens(persona)} tokens")

    print("\n[2] 创建伴侣（落库）")
    created = await service.create(USER_ID, persona)
    print(f"  伴侣 id={created.id} 名称={created.name} 人设版本={created.current_version}")

    print("\n[3] 修改单个维度（新版本）")
    updated = await service.patch_dimension(
        USER_ID, created.id, "speaking_style", "句子短，多用反问，偶尔一句冷幽默。"
    )
    print(f"  版本: {created.current_version} → {updated.current_version}")
    print(f"  新风格: {updated.persona.speaking_style}")

    print("\n[4] 让 AI 只重写一个维度（不保存）")
    value, regen = await service.regenerate_dimension(
        USER_ID, created.id, "speaking_style", "再活泼一点", str(uuid4())
    )
    print(f"  建议值: {value}")
    print(f"  模型: {regen.model_key} | 成本 ≈ ¥{regen.cost_cny:.6f}")

    print("\n[5] 列表与用量")
    records = await service.list(USER_ID)
    print(f"  {USER_ID} 名下伴侣数: {len(records)}")
    summary = await usage_repo.summary(USER_ID, days=1)
    print(
        f"  本日调用 {summary.totals.calls} 次 | 输入 {summary.totals.input_tokens} tokens | "
        f"成本 ≈ ¥{summary.totals.cost_cny:.6f}"
    )
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
