from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.chat import ChatService, InMemoryChatRepository
from app.domain.companions import CompanionService, InMemoryCompanionRepository, LLMResult
from app.domain.memory import InMemoryMemoryRepository
from app.domain.persona import Persona
from app.domain.quota import InMemoryQuotaRepository
from app.domain.usage import CallContext
from app.infra.llm.types import ChatChunk, Usage
from app.infra.summary_repo import InMemorySummaryRepository
from app.main import create_app

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

SUMMARY_TEXT = "用户下周五要去字节面试，最近每天刷两道算法题，情绪偏紧张。"


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        self.calls += 1
        return LLMResult(SUMMARY_TEXT, "fake:summary", Usage(), Decimal("0"))


class FakeStreamer:
    def __init__(self) -> None:
        self.calls: list[list[object]] = []

    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        yield ChatChunk(delta="嗯", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=10, completion_tokens=1))


async def build(budget: int = 120):
    companions = InMemoryCompanionRepository()
    companion_service = CompanionService(companions, FakeLLM())
    record = await companion_service.create("u1", PERSONA)
    repo = InMemoryChatRepository()
    streamer = FakeStreamer()
    summaries = InMemorySummaryRepository()
    llm = FakeLLM()
    service = ChatService(
        repo,
        companion_service,
        streamer,
        summaries=summaries,
        summarizer=llm,
        context_budget_tokens=budget,
    )
    session = await service.create_session("u1", record.id)
    return service, streamer, summaries, llm, session


async def test_long_history_is_summarized_and_injected() -> None:
    service, streamer, summaries, llm, session = await build()
    for index in range(8):
        await service._repo.append_message("u1", session.id, "user", f"第{index}句话" + "很长" * 40)
        await service._repo.append_message("u1", session.id, "assistant", "嗯" + "好" * 40)

    async for _ in service.stream_reply("u1", session.id, "我明天面试", "r1"):
        pass

    system = streamer.calls[0][0]
    assert "# 此前对话摘要" in system.content
    assert SUMMARY_TEXT in system.content
    record = await summaries.get(session.id)
    assert record is not None
    assert record.covered_seq >= 1
    assert llm.calls >= 1


async def test_summary_is_reused_when_coverage_is_sufficient() -> None:
    service, _, summaries, llm, session = await build()
    older = [
        type("M", (), {"seq": 1, "role": "user", "content": "第一句"})(),
        type("M", (), {"seq": 2, "role": "assistant", "content": "回应"})(),
    ]
    first = await service._ensure_summary("u1", session.id, older, "r1")  # type: ignore[arg-type]
    calls_after_first = llm.calls
    again = await service._ensure_summary("u1", session.id, older, "r2")  # type: ignore[arg-type]
    assert first == again == SUMMARY_TEXT
    assert llm.calls == calls_after_first


async def test_recent_messages_are_kept_in_full() -> None:
    service, streamer, _, _, session = await build(budget=100_000)
    await service._repo.append_message("u1", session.id, "user", "我说了一件重要的事")
    async for _ in service.stream_reply("u1", session.id, "还记得吗", "r1"):
        pass
    system = streamer.calls[0][0]
    assert "# 此前对话摘要" not in system.content
    contents = [message.content for message in streamer.calls[0]]
    assert "我说了一件重要的事" in contents


class FakeStreamerApi(FakeStreamer):
    pass


def api_client(budget: int) -> TestClient:
    settings = Settings(  # type: ignore[call-arg]
        env="test", _env_file=None, chat_context_budget_tokens=budget
    )
    app = create_app(
        settings,
        companion_repo=InMemoryCompanionRepository(),
        chat_repo=InMemoryChatRepository(),
        chat_streamer=FakeStreamerApi(),
        llm_client=FakeLLM(),
        memory_repo=InMemoryMemoryRepository(),
        summary_repo=InMemorySummaryRepository(),
        quota_repo=InMemoryQuotaRepository(),
    )
    return TestClient(app)


def test_summary_endpoint_after_long_chat() -> None:
    test_client = api_client(budget=120)
    persona = PERSONA.model_dump()
    companion = test_client.post("/v1/companions", json={"persona": persona}).json()
    session = test_client.post(f"/v1/companions/{companion['id']}/sessions", json={}).json()
    for index in range(4):
        test_client.post(
            f"/v1/sessions/{session['id']}/messages",
            json={"content": f"第{index}句" + "很长的话" * 30},
        )
    summary = test_client.get(f"/v1/sessions/{session['id']}/summary").json()
    assert summary["summary"]
    assert summary["covered_seq"] >= 1


def test_summary_endpoint_returns_empty_for_short_session() -> None:
    test_client = api_client(budget=100_000)
    persona = PERSONA.model_dump()
    companion = test_client.post("/v1/companions", json={"persona": persona}).json()
    session = test_client.post(f"/v1/companions/{companion['id']}/sessions", json={}).json()
    test_client.post(f"/v1/sessions/{session['id']}/messages", json={"content": "你好"})
    summary = test_client.get(f"/v1/sessions/{session['id']}/summary").json()
    assert summary["summary"] is None


async def test_short_history_skips_summary_call() -> None:
    service, _, _, llm, session = await build(budget=100_000)
    await service._repo.append_message("u1", session.id, "user", "你好")
    async for _ in service.stream_reply("u1", session.id, "在吗", "r1"):
        pass
    assert llm.calls == 0
