"""伴侣音色：保存、清空、越权。"""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.templates import TEMPLATES, InMemoryTemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import Usage
from app.main import create_app

PERSONA = {
    "name": "林夏",
    "identity": "心理学研究生",
    "gender": "女",
    "age": 24,
    "personality": ["温柔", "偶尔毒舌"],
    "speaking_style": "句子短，先共情再给建议。",
    "background": "在读心理学研究生，晚上在便利店兼职，见过很多深夜的人。",
    "tags": ["温柔"],
    "relationship": "住在隔壁的学姐",
}


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


def client() -> TestClient:
    return TestClient(
        create_app(
            Settings(env="test", _env_file=None),  # type: ignore[call-arg]
            companion_repo=InMemoryCompanionRepository(),
            template_repo=InMemoryTemplateRepository(TEMPLATES),
            llm_client=FakeLLM(),
        )
    )


def test_set_and_clear_voice() -> None:
    test_client = client()
    companion = test_client.post("/v1/companions", json={"persona": PERSONA}).json()
    assert companion["voice_id"] is None

    saved = test_client.put(
        f"/v1/companions/{companion['id']}/voice",
        json={"voice_id": "BV700_streaming"},
    )
    assert saved.status_code == 200
    assert saved.json()["voice_id"] == "BV700_streaming"

    cleared = test_client.put(f"/v1/companions/{companion['id']}/voice", json={"voice_id": None})
    assert cleared.json()["voice_id"] is None


def test_voice_too_long_rejected() -> None:
    test_client = client()
    companion = test_client.post("/v1/companions", json={"persona": PERSONA}).json()
    response = test_client.put(
        f"/v1/companions/{companion['id']}/voice",
        json={"voice_id": "x" * 200},
    )
    assert response.status_code == 422


def test_set_voice_unknown_companion_404() -> None:
    test_client = client()
    response = test_client.put("/v1/companions/9999/voice", json={"voice_id": "v1"})
    assert response.status_code == 404
