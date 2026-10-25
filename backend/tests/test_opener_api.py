from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.chat import InMemoryChatRepository
from app.domain.companions import InMemoryCompanionRepository, LLMResult
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
    "example_openers": ["这么晚还没睡？"],
}


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


class FakeStreamer:
    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        yield ChatChunk(delta="晚上好，今天怎么样？", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=8, completion_tokens=6))


def client() -> TestClient:
    return TestClient(
        create_app(
            Settings(env="test", _env_file=None),  # type: ignore[call-arg]
            companion_repo=InMemoryCompanionRepository(),
            template_repo=InMemoryTemplateRepository(TEMPLATES),
            chat_repo=InMemoryChatRepository(),
            chat_streamer=FakeStreamer(),
            llm_client=FakeLLM(),
            quota_repo=InMemoryQuotaRepository(),
        )
    )


def prepare(test_client: TestClient) -> int:
    companion = test_client.post("/v1/companions", json={"persona": PERSONA}).json()
    session = test_client.post(f"/v1/companions/{companion['id']}/sessions", json={}).json()
    return session["id"]


def test_opener_and_latest() -> None:
    test_client = client()
    session_id = prepare(test_client)
    companion_id = test_client.get(f"/v1/sessions/{session_id}").json()["companion_id"]

    empty = test_client.get(f"/v1/companions/{companion_id}/latest").json()
    assert empty["content"] is None

    opened = test_client.post(f"/v1/sessions/{session_id}/opener")
    assert opened.status_code == 200
    assert opened.json()["role"] == "assistant"
    assert opened.json()["content"].startswith("晚上好")

    latest = test_client.get(f"/v1/companions/{companion_id}/latest").json()
    assert latest["session_id"] == session_id
    assert latest["content"].startswith("晚上好")

    again = test_client.post(f"/v1/sessions/{session_id}/opener").json()
    assert again["id"] == opened.json()["id"]
    assert len(test_client.get(f"/v1/sessions/{session_id}/messages").json()) == 1
