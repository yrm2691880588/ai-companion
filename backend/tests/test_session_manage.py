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
            quota_repo=InMemoryQuotaRepository(),
        )
    )


def prepare(test_client: TestClient) -> tuple[int, int]:
    companion = test_client.post("/v1/companions", json={"persona": PERSONA}).json()
    session = test_client.post(
        f"/v1/companions/{companion['id']}/sessions", json={"title": "旧标题"}
    ).json()
    return companion["id"], session["id"]


def test_rename_session() -> None:
    test_client = client()
    _companion_id, session_id = prepare(test_client)
    response = test_client.patch(f"/v1/sessions/{session_id}", json={"title": "面试准备"})
    assert response.status_code == 200
    assert response.json()["title"] == "面试准备"
    sessions = test_client.get(f"/v1/companions/{_companion_id}/sessions").json()
    assert sessions[0]["title"] == "面试准备"


def test_delete_message() -> None:
    test_client = client()
    _companion_id, session_id = prepare(test_client)
    test_client.post(f"/v1/sessions/{session_id}/messages", json={"content": "你好"})
    messages = test_client.get(f"/v1/sessions/{session_id}/messages").json()
    assert len(messages) == 2
    response = test_client.delete(f"/v1/messages/{messages[-1]['id']}")
    assert response.status_code == 204
    remaining = test_client.get(f"/v1/sessions/{session_id}/messages").json()
    assert len(remaining) == 1
    assert remaining[0]["role"] == "user"


def test_delete_session_hides_it() -> None:
    test_client = client()
    companion_id, session_id = prepare(test_client)
    assert test_client.delete(f"/v1/sessions/{session_id}").status_code == 204
    assert test_client.get(f"/v1/companions/{companion_id}/sessions").json() == []
    assert test_client.get(f"/v1/sessions/{session_id}").status_code == 404


def test_message_delete_requires_ownership() -> None:
    test_client = client()
    _companion_id, session_id = prepare(test_client)
    test_client.post(f"/v1/sessions/{session_id}/messages", json={"content": "你好"})
    message_id = test_client.get(f"/v1/sessions/{session_id}/messages").json()[0]["id"]
    response = test_client.delete(f"/v1/messages/{message_id}", headers={"X-User-Id": "other"})
    assert response.status_code == 404
