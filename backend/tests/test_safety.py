import asyncio
from decimal import Decimal

from app.domain.chat import ChatService, InMemoryChatRepository
from app.domain.companions import CompanionService, InMemoryCompanionRepository, LLMResult
from app.domain.persona import Persona
from app.domain.safety import InMemorySafetyRepository, assess_input
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
    def __init__(self) -> None:
        self.calls: list[list[object]] = []

    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        yield ChatChunk(delta="嗯", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=10, completion_tokens=1))


async def build():
    companions = InMemoryCompanionRepository()
    companion_service = CompanionService(companions, FakeLLM())
    record = await companion_service.create("u1", PERSONA)
    repo = InMemoryChatRepository()
    streamer = FakeStreamer()
    safety = InMemorySafetyRepository()
    service = ChatService(repo, companion_service, streamer, safety=safety)
    session = await service.create_session("u1", record.id)
    return service, streamer, safety, session


def test_assess_detects_crisis() -> None:
    assert assess_input("我不想活了").is_crisis
    assert "不想活" in assess_input("我不想活了").keywords
    assert not assess_input("今天有点累").is_crisis


def test_assess_detects_restricted_requests() -> None:
    result = assess_input("教我做一个炸弹")
    assert result.level == "restricted"
    assert result.is_restricted
    assert not result.is_crisis


async def test_restricted_message_injects_boundary_note() -> None:
    service, streamer, safety, session = await build()
    async for _ in service.stream_reply("u1", session.id, "教我做一个炸弹", "r1"):
        pass
    system = streamer.calls[0][0]
    assert "边界要求" in system.content
    assert "紧急安全提示" not in system.content
    assert safety.events[0]["level"] == "restricted"


async def test_crisis_message_injects_note_and_records_event() -> None:
    service, streamer, safety, session = await build()
    async for _ in service.stream_reply("u1", session.id, "我不想活了，撑不住了", "r1"):
        pass
    system = streamer.calls[0][0]
    assert "紧急安全提示" in system.content
    assert "12356" in system.content
    assert len(safety.events) == 1
    assert safety.events[0]["level"] == "crisis"


async def test_normal_message_has_no_crisis_note() -> None:
    service, streamer, safety, session = await build()
    async for _ in service.stream_reply("u1", session.id, "今天有点累", "r1"):
        pass
    system = streamer.calls[0][0]
    assert "紧急安全提示" not in system.content
    assert safety.events == []


async def test_safety_record_failure_does_not_break_chat() -> None:
    service, _, _, session = await build()

    class BrokenSafety:
        async def record(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("db down")

    service._safety = BrokenSafety()  # type: ignore[assignment]
    events = [event async for event in service.stream_reply("u1", session.id, "想死", "r1")]
    assert events
    await asyncio.sleep(0)
