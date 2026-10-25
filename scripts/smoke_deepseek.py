"""真实调用 DeepSeek 官方 API 的冒烟脚本：验证模型可用、流式、缓存命中与成本。

运行方式（仓库根目录）：
    backend/.venv/Scripts/python.exe scripts/smoke_deepseek.py

脚本不会打印 API Key；读取 .env 里的 AI_COMPANION_* 配置。
"""

from __future__ import annotations

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.domain.usage import CallContext  # noqa: E402
from app.infra.db import build_engine, build_session_factory  # noqa: E402
from app.infra.llm.gateway import LLMGateway, StreamTelemetry  # noqa: E402
from app.infra.llm.registry import ModelRegistry  # noqa: E402
from app.infra.llm.router import ModelRouter  # noqa: E402
from app.infra.llm.types import Message, Role, TaskName, Usage  # noqa: E402
from app.infra.usage_repo import SqlUsageRepository  # noqa: E402

USER_ID = "dev-user"

SYSTEM = (
    "你是林夏，24 岁，学心理学的学姐，性格温柔但偶尔毒舌，说话口语化、句子短，"
    "习惯先共情再给建议，不用列表和感叹号堆砌，不主动说教。"
    "你正在和一位刚下班的用户聊天。"
)


async def list_models(base_url: str, api_key: str) -> list[str]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            base_url.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        payload = response.json()
    return [item.get("id", "") for item in payload.get("data", [])]


async def run_round(
    router: ModelRouter,
    messages: list[Message],
    *,
    task: TaskName = TaskName.CHAT_MAIN,
) -> tuple[str, Usage | None]:
    telemetry = StreamTelemetry()
    usage: Usage | None = None
    text = ""
    model_key = ""
    async for chunk in router.stream(
        task,
        messages,
        telemetry=telemetry,
        context=CallContext(user_id=USER_ID, request_id=str(uuid4()), task=task),
    ):
        model_key = model_key or (chunk.model_key or "")
        text += chunk.delta
        if chunk.usage is not None:
            usage = chunk.usage
    print(f"  模型: {model_key} | 首字: {telemetry.first_token_ms} ms | 总耗时: {telemetry.total_ms} ms")
    return text, usage


def report_usage(label: str, usage: Usage | None, cost: Decimal | None) -> None:
    if usage is None:
        print(f"  {label}: 未返回 usage")
        return
    print(
        f"  {label}: 输入 {usage.prompt_tokens} tokens "
        f"(命中 {usage.cache_hit_tokens} / 未命中 {usage.cache_miss_tokens}) | "
        f"输出 {usage.completion_tokens} tokens | 成本 ≈ ¥{cost:.6f}"
    )


async def main() -> int:
    settings = get_settings()
    if not settings.master_key:
        print("警告：未配置 AI_COMPANION_MASTER_KEY（本次只验证调用）")
    registry = ModelRegistry.from_presets(keys=settings.provider_keys())
    provider = registry.provider("deepseek")
    if not provider.api_key:
        print("失败：未配置 AI_COMPANION_DEEPSEEK_API_KEY")
        return 1
    spec = registry.model("deepseek:deepseek-flash")
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    repo = SqlUsageRepository(session_factory)
    gateway = LLMGateway(timeout_seconds=120)
    router = ModelRouter(
        registry,
        gateway,
        turn_cost_cap_cny=settings.turn_cost_cap_cny,
        hit_ratio=settings.default_hit_ratio,
        recorder=repo,
    )

    print(f"供应商: {provider.name} | 地址: {provider.base_url}")
    print(f"默认模型: {spec.model_name} | 窗口 {spec.context_window} | 最大输出 {spec.max_output}")

    print("\n[1] 模型列表（GET /models）")
    models = await list_models(provider.base_url, provider.api_key)
    print("  可用模型:", ", ".join(models))

    messages = [
        Message(role=Role.SYSTEM, content=SYSTEM),
        Message(role=Role.USER, content="今天开会被领导当众否了，有点难受。"),
    ]

    print("\n[2] 第一次对话（应触发缓存未命中为主）")
    text1, usage1 = await run_round(router, messages)
    report_usage("第一次", usage1, router.estimated_cost(spec, usage1) if usage1 else None)
    print("  回复:", text1[:120].replace("\n", " "))

    print("\n[3] 相同前缀第二次对话（应出现缓存命中）")
    text2, usage2 = await run_round(router, messages)
    report_usage("第二次", usage2, router.estimated_cost(spec, usage2) if usage2 else None)
    print("  回复:", text2[:120].replace("\n", " "))

    print("\n[4] 记忆抽取（JSON 模式，任务 memory_extract）")
    extract_messages = [
        Message(
            role=Role.SYSTEM,
            content="从用户的话里抽取可长期记住的事实，输出 JSON：{\"items\":[{\"type\":\"喜好|经历|习惯|约定\",\"content\":\"...\"}]}",
        ),
        Message(role=Role.USER, content="我下周五要去字节面试，最近在刷算法题。"),
    ]
    raw, usage3 = await run_round(router, extract_messages, task=TaskName.MEMORY_EXTRACT)
    try:
        parsed = json.loads(raw)
        print("  JSON 解析成功，条数:", len(parsed.get("items", [])))
    except json.JSONDecodeError as exc:
        print("  JSON 解析失败:", exc)
    report_usage("抽取", usage3, router.estimated_cost(spec, usage3) if usage3 else None)

    print("\n[5] 长前缀缓存（约 600+ tokens 的稳定人设，间隔 3 秒调两次）")
    long_system = SYSTEM + "\n背景记忆：\n" + "".join(
        f"{i}、用户习惯在周三晚上复盘工作，喜欢喝冰美式，讨厌被催促，"
        f"和同事小周关系不错，最近在准备下周五的面试。\n"
        for i in range(12)
    )
    cached_messages = [
        Message(role=Role.SYSTEM, content=long_system),
        Message(role=Role.USER, content="你还记得我上周说的事吗？"),
    ]
    _, cache_first = await run_round(router, cached_messages)
    report_usage("第一次", cache_first, router.estimated_cost(spec, cache_first) if cache_first else None)
    await asyncio.sleep(3)
    _, cache_second = await run_round(router, cached_messages)
    report_usage(
        "第二次", cache_second, router.estimated_cost(spec, cache_second) if cache_second else None
    )
    if cache_second and cache_second.cache_hit_tokens:
        print("  结论: 缓存命中率 = %.0f%%" % (cache_second.hit_ratio * 100))
    else:
        print("  结论: 本次未观测到缓存命中（前缀过短或缓存尚未生效）")

    print("\n[6] 延迟采样（5 次短问，用于校准首字 P95）")
    latencies: list[int] = []
    for index in range(5):
        telemetry = StreamTelemetry()
        async for _ in router.stream(
            TaskName.CHAT_MAIN,
            [Message(role=Role.USER, content=f"在吗（第 {index + 1} 次）")],
            telemetry=telemetry,
            context=CallContext(user_id=USER_ID, request_id=str(uuid4()), task=TaskName.CHAT_MAIN),
        ):
            pass
        if telemetry.first_token_ms is not None:
            latencies.append(telemetry.first_token_ms)
    if latencies:
        ordered = sorted(latencies)
        median = ordered[len(ordered) // 2]
        print(f"  首字延迟采样: {latencies} ms | 中位数 {median} ms | 最大 {max(latencies)} ms")

    summary = await repo.summary(USER_ID, days=1)
    print("\n[7] 数据库记账汇总（GET /v1/me/usage/models 同源）")
    print(
        f"  总计: {summary.totals.calls} 次调用（成功 {summary.totals.ok_calls}） | "
        f"输入 {summary.totals.input_tokens} tokens（命中 {summary.totals.cache_hit_tokens}） | "
        f"输出 {summary.totals.output_tokens} tokens | 成本 ≈ ¥{summary.totals.cost_cny:.6f}"
    )
    for item in summary.by_model:
        print(
            f"  - {item.model_key}: {item.totals.calls} 次 | 首字均值 "
            f"{round(item.avg_first_token_ms) if item.avg_first_token_ms else '-'} ms | "
            f"¥{item.totals.cost_cny:.6f}"
        )

    costs = [
        router.estimated_cost(spec, usage)
        for usage in (usage1, usage2, usage3, cache_first, cache_second)
        if usage
    ]
    if costs:
        print(f"\n本轮合计成本 ≈ ¥{sum(costs):.6f}")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
