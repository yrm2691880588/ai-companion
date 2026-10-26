"""试聊：3 轮上限、不落库、不扣额度。"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.chat import InMemoryChatRepository
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.persona import Persona
from app.domain.quota import InMemoryQuotaRepository
from app.domain.trial import MAX_TRIAL_TURNS, TrialService
from app.domain.usage import CallContext
from app.infra.llm.types import ChatChunk, Usage
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


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


class FakeStreamer:
    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        yield ChatChunk(delta="嗯，", model_key="fake:model")
        yield ChatChunk(delta="我在听。", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=10, completion_tokens=4))


def client(streamer: FakeStreamer) -> TestClient:
    return TestClient(
        create_app(
            Settings(env="test", _env_file=None),  # type: ignore[call-arg]
            companion_repo=InMemoryCompanionRepository(),
            chat_repo=InMemoryChatRepository(),
            chat_streamer=streamer,
            llm_client=FakeLLM(),
            quota_repo=InMemoryQuotaRepository(),
        )
    )


def test_trial_three_turns_then_limit() -> None:
    streamer = FakeStreamer()
    test_client = client(streamer)
    trial_id = None
    for turn in range(MAX_TRIAL_TURNS):
        payload = {"persona": PERSONA.model_dump(mode="json"), "content": f"第{turn + 1}句"}
        if trial_id:
            payload["trial_id"] = trial_id
        response = test_client.post("/v1/trial/chat", json=payload)
        assert response.status_code == 200
        assert "event: delta" in response.text
        if trial_id is None:
            import re

            match = re.search(r'"trial_id":\s*"([^"]+)"', response.text)
            assert match
            trial_id = match.group(1)

    blocked = test_client.post(
        "/v1/trial/chat",
        json={
            "persona": PERSONA.model_dump(mode="json"),
            "content": "第四句",
            "trial_id": trial_id,
        },
    )
    assert blocked.status_code == 200
    assert "TRIAL_LIMIT" in blocked.text


def test_trial_does_not_write_database() -> None:
    streamer = FakeStreamer()
    chat_repo = InMemoryChatRepository()
    app = create_app(
        Settings(env="test", _env_file=None),  # type: ignore[call-arg]
        companion_repo=InMemoryCompanionRepository(),
        chat_repo=chat_repo,
        chat_streamer=streamer,
        llm_client=FakeLLM(),
        quota_repo=InMemoryQuotaRepository(),
    )
    test_client = TestClient(app)
    response = test_client.post(
        "/v1/trial/chat",
        json={"persona": PERSONA.model_dump(mode="json"), "content": "你好"},
    )
    assert response.status_code == 200
    assert chat_repo.sessions == {}
    assert chat_repo.messages == {}


def test_trial_rejects_empty_message() -> None:
    test_client = client(FakeStreamer())
    response = test_client.post(
        "/v1/trial/chat",
        json={"persona": PERSONA.model_dump(mode="json"), "content": ""},
    )
    assert response.status_code == 422


async def test_trial_service_rejects_persona_change() -> None:
    service = TrialService(FakeStreamer())
    events = [
        event async for event in service.chat("u1", PERSONA, "你好", trial_id=None, request_id="r1")
    ]
    trial_id = events[0].trial_id
    changed = PERSONA.model_copy(update={"name": "另一个人"})
    with pytest.raises(AppError) as excinfo:
        [
            event
            async for event in service.chat(
                "u1", changed, "换人", trial_id=trial_id, request_id="r2"
            )
        ]
    assert excinfo.value.code == "TRIAL_PERSONA_CHANGED"
