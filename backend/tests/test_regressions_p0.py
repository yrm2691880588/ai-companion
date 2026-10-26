"""针对墓碑与试聊边界的回归测试（先暴露问题，再修）。"""

from decimal import Decimal

import pytest

from app.core.errors import AppError
from app.domain.chat import ChatService, InMemoryChatRepository
from app.domain.companions import CompanionService, InMemoryCompanionRepository, LLMResult
from app.domain.persona import Persona
from app.domain.trial import TrialService
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
    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        yield ChatChunk(delta="嗯。", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=5, completion_tokens=2))


async def build_chat():
    companions = InMemoryCompanionRepository()
    companion_service = CompanionService(companions, FakeLLM())
    record = await companion_service.create("u1", PERSONA)
    repo = InMemoryChatRepository()
    service = ChatService(repo, companion_service, FakeStreamer())
    session = await service.create_session("u1", record.id)
    return service, repo, session


async def test_deleted_message_cannot_be_regenerated() -> None:
    service, repo, session = await build_chat()
    [event async for event in service.stream_reply("u1", session.id, "你好", "r1")]
    assistant = (await service.list_messages("u1", session.id))[-1]
    await service.delete_message("u1", assistant.id)
    with pytest.raises(AppError):
        [event async for event in service.regenerate("u1", assistant.id, "r2")]


async def test_deleted_message_cannot_be_updated() -> None:
    service, repo, session = await build_chat()
    [event async for event in service.stream_reply("u1", session.id, "你好", "r1")]
    assistant = (await service.list_messages("u1", session.id))[-1]
    await service.delete_message("u1", assistant.id)
    assert await repo.update_message("u1", assistant.id, "被改回来了") is None


async def test_unknown_trial_id_is_rejected() -> None:
    service = TrialService(FakeStreamer())
    with pytest.raises(AppError) as excinfo:
        [
            event
            async for event in service.chat(
                "u1", PERSONA, "你好", trial_id="NOT_EXIST", request_id="r1"
            )
        ]
    assert excinfo.value.code == "TRIAL_NOT_FOUND"


async def test_trial_daily_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TrialService(FakeStreamer(), daily_limit=2)
    for _ in range(2):
        [
            event
            async for event in service.chat("u1", PERSONA, "你好", trial_id=None, request_id="r")
        ]
    with pytest.raises(AppError) as excinfo:
        [
            event
            async for event in service.chat("u1", PERSONA, "再来", trial_id=None, request_id="r")
        ]
    assert excinfo.value.code == "TRIAL_DAILY_LIMIT"
