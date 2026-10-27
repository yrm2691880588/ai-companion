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


class FakeStreamer:
    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        self.calls += 1
        yield ChatChunk(delta="先别", model_key="fake:model")
        yield ChatChunk(delta="急着否定自己", usage=Usage(prompt_tokens=20, completion_tokens=8))


def client() -> TestClient:
    app = create_app(
        Settings(local_mode=False, debug_auth=True, env="test", _env_file=None),  # type: ignore[call-arg]
        companion_repo=InMemoryCompanionRepository(),
        template_repo=InMemoryTemplateRepository(TEMPLATES),
        chat_repo=InMemoryChatRepository(),
        chat_streamer=FakeStreamer(),
        llm_client=FakeLLM(),
        quota_repo=InMemoryQuotaRepository(),
    )
    return TestClient(app)


def create_companion(test_client: TestClient) -> int:
    response = test_client.post("/v1/companions", json={"persona": PERSONA})
    assert response.status_code == 201
    return response.json()["id"]


def test_session_and_sse_chat_flow() -> None:
    test_client = client()
    companion_id = create_companion(test_client)
    session = test_client.post(f"/v1/companions/{companion_id}/sessions", json={"title": ""}).json()
    response = test_client.post(
        f"/v1/sessions/{session['id']}/messages", json={"content": "今天被否了"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "event: meta" in body
    assert "event: delta" in body
    assert "event: done" in body
    assert "先别" in body

    messages = test_client.get(f"/v1/sessions/{session['id']}/messages").json()
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "今天被否了"
    assert messages[1]["content"] == "先别急着否定自己"

    sessions = test_client.get(f"/v1/companions/{companion_id}/sessions").json()
    assert len(sessions) == 1
    assert sessions[0]["title"] == "今天被否了"


def test_history_pagination() -> None:
    test_client = client()
    companion_id = create_companion(test_client)
    session_id = test_client.post(f"/v1/companions/{companion_id}/sessions", json={}).json()["id"]
    test_client.post(f"/v1/sessions/{session_id}/messages", json={"content": "第一句"})
    test_client.post(f"/v1/sessions/{session_id}/messages", json={"content": "第二句"})
    all_messages = test_client.get(f"/v1/sessions/{session_id}/messages").json()
    assert len(all_messages) == 4
    latest_two = test_client.get(f"/v1/sessions/{session_id}/messages?limit=2").json()
    assert [item["seq"] for item in latest_two] == [3, 4]


def test_session_is_isolated_between_users() -> None:
    test_client = client()
    companion_id = create_companion(test_client)
    session_id = test_client.post(f"/v1/companions/{companion_id}/sessions", json={}).json()["id"]
    other = test_client.get(f"/v1/sessions/{session_id}", headers={"X-User-Id": "u2"})
    assert other.status_code == 404


def test_delete_session() -> None:
    test_client = client()
    companion_id = create_companion(test_client)
    session_id = test_client.post(f"/v1/companions/{companion_id}/sessions", json={}).json()["id"]
    assert test_client.delete(f"/v1/sessions/{session_id}").status_code == 204
    assert test_client.get(f"/v1/sessions/{session_id}").status_code == 404
