import asyncio
from decimal import Decimal

from app.domain.chat import ChatDelta, ChatDone, ChatService, InMemoryChatRepository
from app.domain.companions import CompanionService, InMemoryCompanionRepository, LLMResult
from app.domain.memory import MemoryRecord
from app.domain.persona import Persona
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


class FakeMemory:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.remembered: list[list[tuple[str, str]]] = []

    async def recall(self, user_id, companion_id, query, *, limit=6):  # type: ignore[no-untyped-def]
        self.queries.append(query)
        return [
            MemoryRecord(
                id=1,
                user_id=user_id,
                companion_id=companion_id,
                type="promise",
                content="下周五要去参加行业会议",
            )
        ]

    async def remember(self, user_id, companion_id, session_id, turns, request_id):  # type: ignore[no-untyped-def]
        self.remembered.append(list(turns))
        return []


async def build():  # type: ignore[no-untyped-def]
    companions = InMemoryCompanionRepository()
    companion_service = CompanionService(companions, FakeLLM())
    record = await companion_service.create("u1", PERSONA)
    repo = InMemoryChatRepository()
    streamer = FakeStreamer()
    memory = FakeMemory()
    service = ChatService(repo, companion_service, streamer, memory)
    session = await service.create_session("u1", record.id)
    return service, streamer, memory, record, session


async def test_recall_is_injected_into_system_prompt() -> None:
    service, streamer, memory, _, session = await build()
    async for _ in service.stream_reply("u1", session.id, "明天面试好紧张", "r1"):
        pass
    assert memory.queries == ["明天面试好紧张"]
    system = streamer.calls[0][0]
    assert "下周五要去参加行业会议" in system.content
    assert "# 你记得的事" in system.content


async def test_remember_is_scheduled_after_reply() -> None:
    service, _, memory, _, session = await build()
    async for _ in service.stream_reply("u1", session.id, "我下周五要去参加行业会议", "r1"):
        pass
    await asyncio.sleep(0)
    assert memory.remembered
    turns = memory.remembered[0]
    assert any(role == "user" and "下周五" in content for role, content in turns)
    assert any(role == "assistant" for role, _ in turns)


async def test_memory_disabled_skips_recall_and_remember() -> None:
    companions = InMemoryCompanionRepository()
    companion_service = CompanionService(companions, FakeLLM())
    record = await companion_service.create("u1", PERSONA)
    record.memory_enabled = False
    repo = InMemoryChatRepository()
    streamer = FakeStreamer()
    memory = FakeMemory()
    service = ChatService(repo, companion_service, streamer, memory)
    session = await service.create_session("u1", record.id)
    events = [event async for event in service.stream_reply("u1", session.id, "你好", "r1")]
    await asyncio.sleep(0)
    assert memory.queries == []
    assert memory.remembered == []
    assert any(isinstance(event, ChatDelta) for event in events)
    assert isinstance(events[-1], ChatDone)
