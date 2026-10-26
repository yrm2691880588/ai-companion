"""人设导入：合法创建、字段缺失、格式错误、版本过新。"""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.templates import TEMPLATES, InMemoryTemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import Usage
from app.main import create_app

PERSONA = {
    "name": "导入测试",
    "identity": "图书管理员",
    "gender": "女",
    "age": 28,
    "personality": ["安静", "耐心"],
    "speaking_style": "句子短，语速慢，喜欢用比喻。",
    "background": "在城南图书馆工作六年，熟悉每一排书架，午休时会在窗边看闲书。",
    "tags": ["图书管理员"],
    "relationship": "常在图书馆遇到的姐姐",
    "example_openers": ["又来借书？"],
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


def test_import_creates_companion() -> None:
    test_client = client()
    response = test_client.post(
        "/v1/personas/import",
        json={"format": "ai-companion-persona", "version": 1, "persona": PERSONA},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "导入测试"
    assert body["persona"]["identity"] == "图书管理员"


def test_import_rejects_missing_field() -> None:
    test_client = client()
    broken = dict(PERSONA)
    broken.pop("speaking_style")
    response = test_client.post("/v1/personas/import", json={"persona": broken})
    assert response.status_code == 422


def test_import_rejects_unknown_format() -> None:
    test_client = client()
    response = test_client.post(
        "/v1/personas/import",
        json={"format": "other-format", "persona": PERSONA},
    )
    assert response.status_code == 422


def test_import_rejects_future_version() -> None:
    test_client = client()
    response = test_client.post(
        "/v1/personas/import",
        json={"format": "ai-companion-persona", "version": 99, "persona": PERSONA},
    )
    assert response.status_code == 422


def test_import_allows_custom_name() -> None:
    test_client = client()
    response = test_client.post(
        "/v1/personas/import",
        json={"persona": PERSONA, "name": "换名版"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "换名版"
