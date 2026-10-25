from decimal import Decimal

import pytest

from app.core.errors import AppError
from app.domain.chat import ChatService, InMemoryChatRepository
from app.domain.companions import CompanionService, InMemoryCompanionRepository, LLMResult
from app.domain.persona import Persona
from app.domain.quota import InMemoryQuotaRepository, QuotaService
from app.domain.usage import CallContext
from app.infra.llm.types import ChatChunk, Usage

PERSONA = Persona.model_validate(
    {
        "name": "林夏",
        "identity": "心理学研究生",
        "gender": "女",
        "age": 24,
        "personality": ["温柔", "偶尔毒舌"],
        "speaking_style": "句子短，先共情再给建议。",
        "background": "在读心理学研究生，晚上在便利店兼职，见过很多深夜的人。",
        "tags": ["温柔", "学姐"],
        "relationship": "住在隔壁的学姐",
    }
)


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


class FakeStreamer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        if self.fail:
            raise RuntimeError("upstream down")
        yield ChatChunk(delta="嗯", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=1, completion_tokens=1))


async def build(limit: int = 2, fail: bool = False):
    companions = InMemoryCompanionRepository()
    companion_service = CompanionService(companions, FakeLLM())
    record = await companion_service.create("u1", PERSONA)
    quota = QuotaService(InMemoryQuotaRepository(), daily_limit=limit)
    service = ChatService(
        InMemoryChatRepository(), companion_service, FakeStreamer(fail), quota=quota
    )
    session = await service.create_session("u1", record.id)
    return service, quota, session


async def test_quota_counts_chat_turns() -> None:
    service, quota, session = await build(limit=2)
    await service.ensure_quota("u1")
    [event async for event in service.stream_reply("u1", session.id, "你好", "r1")]
    state = await quota.status("u1")
    assert state.used == 1
    assert state.remaining == 1


async def test_quota_exceeded_raises() -> None:
    service, quota, session = await build(limit=1)
    [event async for event in service.stream_reply("u1", session.id, "第一句", "r1")]
    with pytest.raises(AppError) as excinfo:
        [event async for event in service.stream_reply("u1", session.id, "第二句", "r2")]
    assert excinfo.value.code == "QUOTA_EXCEEDED"
    assert (await quota.status("u1")).used == 1


async def test_failure_before_first_token_refunds() -> None:
    service, quota, session = await build(limit=5, fail=True)
    with pytest.raises(RuntimeError):
        [event async for event in service.stream_reply("u1", session.id, "你好", "r1")]
    assert (await quota.status("u1")).used == 0


async def test_ensure_available_rejects_when_exhausted() -> None:
    quota = QuotaService(InMemoryQuotaRepository(), daily_limit=1)
    await quota.consume("u1")
    with pytest.raises(AppError) as excinfo:
        await quota.ensure_available("u1")
    assert excinfo.value.status_code == 429


async def test_limit_is_per_user() -> None:
    quota = QuotaService(InMemoryQuotaRepository(), daily_limit=1)
    await quota.consume("u1")
    state = await quota.status("u2")
    assert state.used == 0
