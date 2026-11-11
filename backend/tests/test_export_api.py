import json
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.chat import InMemoryChatRepository
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.memory import InMemoryMemoryRepository
from app.domain.quota import InMemoryQuotaRepository
from app.domain.templates import TEMPLATES, InMemoryTemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import ChatChunk, Usage
from app.main import create_app

PERSONA = {
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

MEMORY_JSON = json.dumps(
    {
        "items": [
            {
                "type": "promise",
                "content": "下周五要去参加行业会议",
                "confidence": 0.9,
                "quote": "我下周五要去参加行业会议",
            }
        ]
    },
    ensure_ascii=False,
)


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult(MEMORY_JSON, "fake:model", Usage(), Decimal("0"))


class FakeStreamer:
    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        yield ChatChunk(delta="在的", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=5, completion_tokens=1))


def client() -> TestClient:
    return TestClient(
        create_app(
            Settings(local_mode=False, debug_auth=True, env="test", _env_file=None),  # type: ignore[call-arg]
            companion_repo=InMemoryCompanionRepository(),
            template_repo=InMemoryTemplateRepository(TEMPLATES),
            chat_repo=InMemoryChatRepository(),
            chat_streamer=FakeStreamer(),
            llm_client=FakeLLM(),
            memory_repo=InMemoryMemoryRepository(),
            quota_repo=InMemoryQuotaRepository(),
        )
    )


def test_export_contains_companion_sessions_messages_and_memories() -> None:
    test_client = client()
    companion = test_client.post("/v1/companions", json={"persona": PERSONA}).json()
    session = test_client.post(f"/v1/companions/{companion['id']}/sessions", json={}).json()
    test_client.post(f"/v1/sessions/{session['id']}/messages", json={"content": "我下周五要面试"})
    test_client.post(f"/v1/sessions/{session['id']}/memories/extract")

    payload = test_client.get("/v1/me/export").json()
    assert payload["user_id"] == "dev-user"
    assert len(payload["companions"]) == 1
    exported = payload["companions"][0]
    assert exported["name"] == "林夏"
    assert exported["persona"]["identity"] == "心理学研究生"
    assert len(exported["sessions"]) == 1
    assert len(exported["sessions"][0]["messages"]) == 2
    assert exported["memories"][0]["content"] == "下周五要去参加行业会议"


def test_export_does_not_leak_other_users() -> None:
    test_client = client()
    test_client.post("/v1/companions", json={"persona": PERSONA})
    payload = test_client.get("/v1/me/export", headers={"X-User-Id": "u2"}).json()
    assert payload["companions"] == []
