import json
from decimal import Decimal

import pytest

from app.core.errors import AppError, InvalidInput
from app.domain.chat import InMemoryChatRepository
from app.domain.companions import CompanionService, InMemoryCompanionRepository, LLMResult
from app.domain.persona import Persona
from app.domain.roleplay import (
    SCENARIOS,
    InMemoryRunRepository,
    InMemoryScenarioRepository,
    RoleplayService,
    parse_review,
)
from app.domain.usage import CallContext
from app.infra.llm.types import ChatChunk, Usage

PERSONA = Persona.model_validate(
    {
        "name": "何静",
        "identity": "HRBP",
        "gender": "女",
        "age": 32,
        "personality": ["专业", "敏锐"],
        "speaking_style": "一次问一个问题。",
        "background": "做过五年招聘，面试过上千人，现在做面试辅导。",
        "tags": ["面试", "HR"],
        "relationship": "你的模拟面试官",
    }
)

REVIEW = json.dumps(
    {
        "summary": "表达清楚，但缺少结果数据。",
        "scores": {"clarity": 4, "empathy": 3, "structure": 3, "confidence": 4},
        "highlights": ["开场简洁", "能承认不确定"],
        "improvements": ["补充量化结果", "回答前先想结构"],
        "sample_lines": ["我负责的那部分把转化率从 3% 提到 4.2%。"],
    },
    ensure_ascii=False,
)


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        self.calls += 1
        return LLMResult(REVIEW, "fake:review", Usage(), Decimal("0.0001"))


class FakeStreamer:
    def __init__(self) -> None:
        self.calls: list[list[object]] = []

    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        yield ChatChunk(delta="先做个自我介绍吧。", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=10, completion_tokens=5))


async def build():
    companions = InMemoryCompanionRepository()
    companion_service = CompanionService(companions, FakeLLM())
    record = await companion_service.create("u1", PERSONA)
    chat = InMemoryChatRepository()
    scenarios = InMemoryScenarioRepository(SCENARIOS)
    runs = InMemoryRunRepository()
    llm = FakeLLM()
    streamer = FakeStreamer()
    service = RoleplayService(scenarios, runs, chat, companion_service, streamer, llm)
    return service, chat, runs, llm, streamer, record


async def test_start_creates_run_session_and_opening() -> None:
    service, chat, _, _, _, record = await build()
    run, session, opening = await service.start("u1", record.id, "interview_screen")
    assert run.status == "active"
    assert run.max_turns == 8
    assert opening.role == "assistant"
    assert "自我介绍" in opening.content
    messages = await chat.list_messages("u1", session.id)
    assert len(messages) == 1


async def test_turn_streams_and_increments() -> None:
    service, chat, runs, _, streamer, record = await build()
    run, session, _ = await service.start("u1", record.id, "interview_screen")
    events = [event async for event in service.stream_turn("u1", run.id, "你好，我叫小林。", "r1")]
    assert events
    messages = await chat.list_messages("u1", session.id)
    assert [item.role for item in messages] == ["assistant", "user", "assistant"]
    updated = await runs.get("u1", run.id)
    assert updated is not None and updated.turns_played == 1
    system = streamer.calls[0][0]
    assert "只以角色身份说话" in system.content


async def test_turn_limit_is_enforced() -> None:
    service, _, _, _, _, record = await build()
    run, _, _ = await service.start("u1", record.id, "stranger_talk", max_turns=1)
    [event async for event in service.stream_turn("u1", run.id, "你好", "r1")]
    with pytest.raises(InvalidInput) as excinfo:
        [event async for event in service.stream_turn("u1", run.id, "在吗", "r2")]
    assert excinfo.value.code == "ROLEPLAY_MAX_TURNS"


async def test_finish_generates_review_and_is_idempotent() -> None:
    service, _, _, llm, _, record = await build()
    run, _, _ = await service.start("u1", record.id, "interview_screen")
    [event async for event in service.stream_turn("u1", run.id, "我负责过一个项目。", "r1")]
    finished = await service.finish("u1", run.id, "r2")
    assert finished.status == "finished"
    assert finished.review is not None
    assert finished.review["scores"]["clarity"] == 4
    assert llm.calls == 1
    again = await service.finish("u1", run.id, "r3")
    assert again.review == finished.review
    assert llm.calls == 1


async def test_other_user_cannot_access_run() -> None:
    service, _, _, _, _, record = await build()
    run, _, _ = await service.start("u1", record.id, "interview_screen")
    with pytest.raises(AppError):
        await service.get("u2", run.id)


async def test_unknown_scenario_returns_404() -> None:
    service, _, _, _, _, record = await build()
    with pytest.raises(AppError):
        await service.start("u1", record.id, "nope")


def test_parse_review_clamps_scores() -> None:
    review = parse_review(
        '{"summary":"ok","scores":{"clarity":9,"empathy":0},"highlights":["a"],'
        '"improvements":["b"],"sample_lines":["c"]}'
    )
    assert review["scores"]["clarity"] == 5
    assert review["scores"]["empathy"] == 1


def test_parse_review_falls_back_on_bad_json() -> None:
    review = parse_review("这不是 JSON")
    assert review["summary"] == "这不是 JSON"
    assert review["highlights"] == []


def test_parse_review_handles_raw_newlines_inside_strings() -> None:
    text = '{"summary":"第一行\n第二行","scores":{"clarity":4}}'
    review = parse_review(text)
    assert review["scores"]["clarity"] == 4
    assert "第一行" in str(review["summary"])
