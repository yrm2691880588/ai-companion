"""P0.5：记忆提示（done.memories）与回访承接（summary）。"""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.chat import InMemoryChatRepository
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.memory import InMemoryMemoryRepository
from app.domain.persona import Persona
from app.domain.quota import InMemoryQuotaRepository
from app.domain.templates import TEMPLATES, InMemoryTemplateRepository
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
    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        yield ChatChunk(delta="嗯。", model_key="fake:model")
        yield ChatChunk(usage=Usage(prompt_tokens=5, completion_tokens=2))


def build():
    memories = InMemoryMemoryRepository()
    app = create_app(
        Settings(env="test", _env_file=None),  # type: ignore[call-arg]
        companion_repo=InMemoryCompanionRepository(),
        template_repo=InMemoryTemplateRepository(TEMPLATES),
        chat_repo=InMemoryChatRepository(),
        chat_streamer=FakeStreamer(),
        llm_client=FakeLLM(),
        memory_repo=memories,
        quota_repo=InMemoryQuotaRepository(),
    )
    return TestClient(app), memories


async def test_done_event_contains_recalled_memories() -> None:
    test_client, memories = build()
    companion = test_client.post("/v1/companions", json={"persona": PERSONA.model_dump()}).json()
    session = test_client.post(f"/v1/companions/{companion['id']}/sessions", json={}).json()
    # 直接写入一条记忆，确保召回
    await memories.add(
        "dev-user",
        companion["id"],
        type="habit",
        content="每天刷算法题",
        confidence=0.9,
        quote=None,
        source_session_id=session["id"],
        source_message_id=None,
    )
    response = test_client.post(
        f"/v1/sessions/{session['id']}/messages",
        json={"content": "今天刷了几道算法题"},
    )
    assert response.status_code == 200
    assert '"memories"' in response.text


def test_summary_endpoint_returns_empty_for_new_session() -> None:
    test_client, _ = build()
    companion = test_client.post("/v1/companions", json={"persona": PERSONA.model_dump()}).json()
    session = test_client.post(f"/v1/companions/{companion['id']}/sessions", json={}).json()
    summary = test_client.get(f"/v1/sessions/{session['id']}/summary").json()
    assert summary["summary"] is None
