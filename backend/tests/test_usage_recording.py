from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.usage import CallContext, InMemoryUsageRepository
from app.infra.llm.registry import ModelRegistry
from app.infra.llm.router import ModelRouter
from app.infra.llm.types import (
    ChatChunk,
    ContentBlocked,
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
    def __init__(self, script: list[object]) -> None:
        self.script = list(script)
        self.calls = 0

    async def astream(self, provider, spec, messages, params, *, telemetry=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if hasattr(item, "__aiter__"):
            async for chunk in item:  # type: ignore[union-attr]
                yield chunk
            return
        for chunk in item:  # type: ignore[union-attr]
            yield chunk


def make_router(gateway: ScriptedGateway, repo: InMemoryUsageRepository) -> ModelRouter:
    return ModelRouter(
        REG,
        gateway,  # type: ignore[arg-type]
        recorder=repo,
        clock=lambda: datetime(2026, 10, 26, 10, 0, tzinfo=SHANGHAI),
    )


def context() -> CallContext:
    return CallContext(user_id="u1", request_id="req-1", task=TaskName.CHAT_MAIN)


async def run(router: ModelRouter) -> str:
    text = ""
    async for chunk in router.stream(
        TaskName.CHAT_MAIN,
        [Message(role=Role.USER, content="今天有点累")],
        context=context(),
    ):
        text += chunk.delta
    return text


async def test_successful_call_is_recorded() -> None:
    repo = InMemoryUsageRepository()
    usage = Usage(prompt_tokens=100, completion_tokens=5, cache_hit_tokens=80, cache_miss_tokens=20)
    gateway = ScriptedGateway([[ChatChunk(delta="你", usage=usage)]])
    text = await run(make_router(gateway, repo))
    assert text == "你"
    assert len(repo.records) == 1
    record = repo.records[0]
    assert record.status == "ok"
    assert record.user_id == "u1"
    assert record.model_key == "deepseek:deepseek-flash"
    assert record.input_tokens == 100
    assert record.completion_tokens == 5
    assert record.hit_ratio == 0.8
    assert record.cost_micros > 0
    assert record.total_ms is not None


async def test_failed_attempt_and_success_are_both_recorded() -> None:
    repo = InMemoryUsageRepository()
    gateway = ScriptedGateway([RateLimited("429"), [ChatChunk(delta="好")]])
    await run(make_router(gateway, repo))
    assert len(repo.records) == 2
    assert repo.records[0].status == "error"
    assert repo.records[0].error_code == "RATE_LIMITED"
    assert repo.records[1].status == "ok"


async def test_aborted_stream_is_recorded() -> None:
    repo = InMemoryUsageRepository()

    async def stream():  # type: ignore[no-untyped-def]
        yield ChatChunk(delta="你")
        raise UpstreamError("boom")

    router = make_router(ScriptedGateway([stream()]), repo)
    with pytest.raises(StreamAborted):
        await run(router)
    assert len(repo.records) == 1
    assert repo.records[0].status == "aborted"
    assert repo.records[0].error_code == "UPSTREAM_ERROR"


async def test_blocked_call_is_recorded() -> None:
    repo = InMemoryUsageRepository()
    router = make_router(ScriptedGateway([ContentBlocked("blocked")]), repo)
    with pytest.raises(ContentBlocked):
        await run(router)
    assert len(repo.records) == 1
    assert repo.records[0].status == "blocked"
