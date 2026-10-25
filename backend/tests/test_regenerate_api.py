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
}


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


class CountingStreamer:
    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        yield ChatChunk(delta=f"回复{self.calls}", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=10, completion_tokens=2))


def client(streamer: CountingStreamer) -> TestClient:
    return TestClient(
        create_app(
            Settings(env="test", _env_file=None),  # type: ignore[call-arg]
            companion_repo=InMemoryCompanionRepository(),
            template_repo=InMemoryTemplateRepository(TEMPLATES),
            chat_repo=InMemoryChatRepository(),
            chat_streamer=streamer,
            llm_client=FakeLLM(),
            quota_repo=InMemoryQuotaRepository(),
        )
    )


def prepare(test_client: TestClient) -> tuple[int, int]:
    companion = test_client.post("/v1/companions", json={"persona": PERSONA}).json()
    session = test_client.post(f"/v1/companions/{companion['id']}/sessions", json={}).json()
    test_client.post(f"/v1/sessions/{session['id']}/messages", json={"content": "你好"})
    messages = test_client.get(f"/v1/sessions/{session['id']}/messages").json()
    return session["id"], messages[-1]["id"]


def test_regenerate_replaces_last_assistant_message() -> None:
    test_client = client(CountingStreamer())
    session_id, assistant_id = prepare(test_client)

    response = test_client.post(f"/v1/messages/{assistant_id}/regenerate")
    assert response.status_code == 200
    assert "event: delta" in response.text
    assert "回复2" in response.text

    messages = test_client.get(f"/v1/sessions/{session_id}/messages").json()
    assert len(messages) == 2
    assert messages[-1]["id"] == assistant_id
    assert messages[-1]["content"] == "回复2"


def test_regenerate_twice_replaces_again() -> None:
    test_client = client(CountingStreamer())
    session_id, assistant_id = prepare(test_client)
    test_client.post(f"/v1/messages/{assistant_id}/regenerate")
    second = test_client.post(f"/v1/messages/{assistant_id}/regenerate")
    assert "回复3" in second.text
    messages = test_client.get(f"/v1/sessions/{session_id}/messages").json()
    assert messages[-1]["content"] == "回复3"
    assert len(messages) == 2


def test_regenerate_rejects_user_message() -> None:
    test_client = client(CountingStreamer())
    session_id, _assistant_id = prepare(test_client)
    messages = test_client.get(f"/v1/sessions/{session_id}/messages").json()
    user_id = next(item["id"] for item in messages if item["role"] == "user")
    response = test_client.post(f"/v1/messages/{user_id}/regenerate")
    assert "REGENERATE_TARGET" in response.text
