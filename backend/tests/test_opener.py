from decimal import Decimal

from app.domain.chat import ChatService, InMemoryChatRepository
from app.domain.companions import CompanionService, InMemoryCompanionRepository, LLMResult
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
        "example_openers": ["这么晚还没睡？", "刚下班，给你带了热牛奶。"],
    }
)


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


class OpenerStreamer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.fail:
            raise RuntimeError("upstream down")
        yield ChatChunk(delta="晚上好，", model_key="fake:model")
        yield ChatChunk(delta="今天过得怎么样？", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=10, completion_tokens=8))


async def build(fail: bool = False):
    companions = InMemoryCompanionRepository()
    companion_service = CompanionService(companions, FakeLLM())
    companion = await companion_service.create("u1", PERSONA)
    streamer = OpenerStreamer(fail)
    service = ChatService(InMemoryChatRepository(), companion_service, streamer)
    session = await service.create_session("u1", companion.id)
    return service, streamer, session


async def test_empty_session_gets_an_opener() -> None:
    service, streamer, session = await build()
    message = await service.open_session("u1", session.id, "r1")
    assert message.role == "assistant"
    assert message.content == "晚上好，今天过得怎么样？"
    assert streamer.calls == 1
    assert len(await service.list_messages("u1", session.id)) == 1


async def test_opener_is_generated_only_once() -> None:
    service, streamer, session = await build()
    first = await service.open_session("u1", session.id, "r1")
    second = await service.open_session("u1", session.id, "r2")
    assert first.id == second.id
    assert streamer.calls == 1
    assert len(await service.list_messages("u1", session.id)) == 1


async def test_opener_falls_back_when_model_fails() -> None:
    service, _, session = await build(fail=True)
    message = await service.open_session("u1", session.id, "r1")
    assert message.content == "这么晚还没睡？"


async def test_opener_does_not_trigger_for_non_empty_session() -> None:
    service, streamer, session = await build()
    await service.open_session("u1", session.id, "r1")
    await service.open_session("u1", session.id, "r2")
    first = (await service.list_messages("u1", session.id))[0]
    assert first.content.startswith("晚上好")
    assert streamer.calls == 1
