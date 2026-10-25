from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.chat import InMemoryChatRepository
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.quota import InMemoryQuotaRepository
from app.domain.system_settings import InMemorySystemSettingsRepository
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
        yield ChatChunk(delta="嗯", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=5, completion_tokens=1))


def client(limit: int) -> TestClient:
    settings_repo = InMemorySystemSettingsRepository()
    settings_repo.value = {"quota": {"enforced": True, "daily_limit": limit}}
    settings = Settings(  # type: ignore[call-arg]
        env="test", _env_file=None, daily_turn_limit=limit
    )
    app = create_app(
        settings,
        companion_repo=InMemoryCompanionRepository(),
        template_repo=InMemoryTemplateRepository(TEMPLATES),
        chat_repo=InMemoryChatRepository(),
        chat_streamer=FakeStreamer(),
        llm_client=FakeLLM(),
        quota_repo=InMemoryQuotaRepository(),
        system_settings_repo=settings_repo,
    )
    # TestClient 不以上下文管理器使用时不会触发 lifespan，这里手动应用配置
    app.state.quota_service.configure(enforced=True, daily_limit=limit)
    return TestClient(app)


def prepare(test_client: TestClient) -> int:
    companion = test_client.post("/v1/companions", json={"persona": PERSONA}).json()
    session = test_client.post(f"/v1/companions/{companion['id']}/sessions", json={}).json()
    return session["id"]


def test_quota_endpoint_reports_remaining() -> None:
    test_client = client(limit=3)
    payload = test_client.get("/v1/me/quota").json()
    assert payload["limit"] == 3
    assert payload["used"] == 0
    assert payload["remaining"] == 3


def test_quota_is_enforced_on_send() -> None:
    test_client = client(limit=1)
    session_id = prepare(test_client)
    first = test_client.post(f"/v1/sessions/{session_id}/messages", json={"content": "你好"})
    assert first.status_code == 200
    second = test_client.post(f"/v1/sessions/{session_id}/messages", json={"content": "再来"})
    assert second.status_code == 429
    assert second.json()["code"] == "QUOTA_EXCEEDED"
    quota = test_client.get("/v1/me/quota").json()
    assert quota["used"] == 1
    assert quota["remaining"] == 0
