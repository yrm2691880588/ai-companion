"""用户身份接口：读写、伴侣覆盖、越权。"""

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


def test_profile_roundtrip() -> None:
    test_client = client()
    response = test_client.put(
        "/v1/me/profile",
        json={
            "nickname": "小周",
            "identity": "后端工程师",
            "age": 27,
            "gender": "男",
            "city": "杭州",
            "background": "在准备考研",
        },
    )
    assert response.status_code == 200
    assert test_client.get("/v1/me/profile").json()["nickname"] == "小周"


def test_companion_profile_override_and_fallback() -> None:
    test_client = client()
    test_client.put("/v1/me/profile", json={"nickname": "小周", "identity": "后端工程师"})
    companion = test_client.post("/v1/companions", json={"persona": PERSONA}).json()

    response = test_client.put(
        f"/v1/me/companions/{companion['id']}/profile",
        json={"identity": "她的学弟"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["identity"] == "她的学弟"
    assert body["effective"]["nickname"] == "小周"


def test_profile_age_validation() -> None:
    test_client = client()
    response = test_client.put("/v1/me/profile", json={"age": 17})
    assert response.status_code == 422
