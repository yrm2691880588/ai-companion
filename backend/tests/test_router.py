from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.infra.llm.registry import ModelRegistry
from app.infra.llm.router import ModelRouter
from app.infra.llm.tokenizer import estimate_messages_tokens
from app.infra.llm.types import (
    AllProvidersFailed,
    ChatChunk,
    ContentBlocked,
    ContextOverflow,
    Message,
    RateLimited,
    Role,
    StreamAborted,
    TaskName,
    UpstreamError,
    Usage,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
REG = ModelRegistry.from_presets(env={})


class ScriptedGateway:
    """按脚本依次返回：异常实例则抛出，否则当作流式分片来源。"""

    def __init__(self, script: list[Any]) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def astream(
        self,
        provider: Any,
        spec: Any,
        messages: Any,
        params: Any,
        *,
        telemetry: Any = None,
    ) -> AsyncIterator[ChatChunk]:
        self.calls.append(
            {"spec": spec, "provider": provider, "messages": list(messages), "params": params}
        )
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if hasattr(item, "__aiter__"):
            async for chunk in item:
                yield chunk
            return
        for chunk in item:
            yield chunk


def make_router(gateway: ScriptedGateway) -> ModelRouter:
    return ModelRouter(
        REG,
        gateway,  # type: ignore[arg-type]
        clock=lambda: datetime(2026, 10, 26, 10, 0, tzinfo=SHANGHAI),
    )


def messages() -> list[Message]:
    return [Message(role=Role.USER, content="今天有点累")]


async def drain(router: ModelRouter) -> list[ChatChunk]:
    return [chunk async for chunk in router.stream(TaskName.CHAT_MAIN, messages())]


async def test_falls_back_before_first_token() -> None:
    gateway = ScriptedGateway([RateLimited("429"), [ChatChunk(delta="好")]])
    chunks = await drain(make_router(gateway))
    assert "".join(chunk.delta for chunk in chunks) == "好"
    assert len(gateway.calls) == 2
    assert gateway.calls[0]["spec"].key == "deepseek:deepseek-flash"
    assert gateway.calls[1]["spec"].key != gateway.calls[0]["spec"].key


async def test_content_block_is_not_retried_elsewhere() -> None:
    gateway = ScriptedGateway([ContentBlocked("blocked")])
    with pytest.raises(ContentBlocked):
        await drain(make_router(gateway))
    assert len(gateway.calls) == 1


async def test_abort_after_first_token_raises_stream_aborted() -> None:
    async def stream() -> AsyncIterator[ChatChunk]:
        yield ChatChunk(delta="你")
        raise UpstreamError("boom")

    gateway = ScriptedGateway([stream()])
    router = make_router(gateway)
    collected = ""
    with pytest.raises(StreamAborted):
        async for chunk in router.stream(TaskName.CHAT_MAIN, messages()):
            collected += chunk.delta
    assert collected == "你"
    assert len(gateway.calls) == 1


async def test_context_overflow_retries_same_model_with_less_context() -> None:
    long_history = [Message(role=Role.USER, content="旧" * 200_000)]
    long_history.append(Message(role=Role.USER, content="最新"))
    gateway = ScriptedGateway([ContextOverflow("too long"), [ChatChunk(delta="ok")]])
    router = make_router(gateway)
    chunks = [chunk async for chunk in router.stream(TaskName.CHAT_MAIN, long_history)]
    assert "".join(chunk.delta for chunk in chunks) == "ok"
    assert len(gateway.calls) == 2
    assert gateway.calls[0]["spec"].key == gateway.calls[1]["spec"].key
    assert estimate_messages_tokens(gateway.calls[1]["messages"]) <= estimate_messages_tokens(
        gateway.calls[0]["messages"]
    )


async def test_all_failures_are_reported() -> None:
    gateway = ScriptedGateway([RateLimited("1"), UpstreamError("2"), RateLimited("3")])
    with pytest.raises(AllProvidersFailed) as excinfo:
        await drain(make_router(gateway))
    assert len(excinfo.value.attempts) == 3


async def test_chunks_are_tagged_with_model() -> None:
    gateway = ScriptedGateway([[ChatChunk(delta="hi")]])
    chunks = await drain(make_router(gateway))
    assert chunks[0].model_key == "deepseek:deepseek-flash"
    assert chunks[0].provider_key == "deepseek"


async def test_budget_is_derived_from_cost_cap() -> None:
    router = make_router(ScriptedGateway([]))
    spec = REG.model("deepseek:deepseek-flash")
    budget = router.budget(spec)
    assert 44_000 <= budget <= 52_000


async def test_usage_cost_uses_real_price() -> None:
    router = make_router(ScriptedGateway([]))
    spec = REG.model("deepseek:deepseek-flash")
    cost = router.estimated_cost(
        spec,
        Usage(
            prompt_tokens=16_000,
            completion_tokens=500,
            cache_hit_tokens=13_600,
            cache_miss_tokens=2_400,
        ),
    )
    assert 0.005 < float(cost) < 0.02


async def test_cost_without_cache_hits_is_not_underestimated() -> None:
    """供应商报 0 命中时必须按未命中价算，不能套用默认命中率。"""
    router = make_router(ScriptedGateway([]))
    spec = REG.model("deepseek:deepseek-flash")
    cost = router.estimated_cost(
        spec,
        Usage(
            prompt_tokens=16_000,
            completion_tokens=500,
            cache_hit_tokens=0,
            cache_miss_tokens=16_000,
        ),
    )
    # 高峰价：16K × ¥2/M + 500 × ¥8/M = ¥0.032 + ¥0.004
    assert cost == pytest.approx(Decimal("0.036"), abs=Decimal("0.0005"))
