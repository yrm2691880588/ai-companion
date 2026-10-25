import json
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.deletion import InMemoryDeletionRepository
from app.domain.templates import TEMPLATES, InMemoryTemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import Message, TaskName, Usage
from app.main import create_app


class FakeLLM:
    async def complete(
        self, task: TaskName, messages: list[Message], *, context: CallContext
    ) -> LLMResult:
        return LLMResult(
            text=json.dumps({"value": "ok"}, ensure_ascii=False),
            model_key="fake:model",
            usage=Usage(prompt_tokens=1, completion_tokens=1),
            cost_cny=Decimal("0"),
        )


def client() -> TestClient:
    app = create_app(
        Settings(env="test", _env_file=None),  # type: ignore[call-arg]
        companion_repo=InMemoryCompanionRepository(),
        template_repo=InMemoryTemplateRepository(TEMPLATES),
        llm_client=FakeLLM(),
        deletion_repo=InMemoryDeletionRepository(),
    )
    return TestClient(app)


def test_templates_list_all_categories() -> None:
    response = client().get("/v1/templates")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 10
    assert {item["category"] for item in payload} == {
        "情感伴侣",
        "职场导师",
        "同事交流",
        "社交演练",
        "学习伙伴",
    }


def test_templates_filter_by_category() -> None:
    payload = client().get("/v1/templates?category=职场导师").json()
    assert len(payload) == 2
    assert all(item["category"] == "职场导师" for item in payload)


def test_template_detail() -> None:
    payload = client().get("/v1/templates/warm_senior").json()
    assert payload["name"] == "温柔学姐"
    assert payload["persona"]["name"] == "林夏"


def test_unknown_template_returns_404() -> None:
    response = client().get("/v1/templates/nope")
    assert response.status_code == 404
    assert response.json()["code"] == "TEMPLATE_NOT_FOUND"


def test_create_companion_from_template_with_custom_name() -> None:
    test_client = client()
    created = test_client.post(
        "/v1/companions/from-template",
        json={"template_key": "study_buddy", "name": "小林"},
    )
    assert created.status_code == 201
    payload = created.json()
    assert payload["name"] == "小林"
    assert payload["persona"]["name"] == "小林"
    assert payload["persona"]["identity"] == "二战考研的搭子"
    assert payload["current_version"] == 1


def test_delete_companion_requires_matching_name() -> None:
    test_client = client()
    created = test_client.post(
        "/v1/companions/from-template", json={"template_key": "warm_senior"}
    ).json()
    mismatch = test_client.delete(f"/v1/companions/{created['id']}?confirm_name=错名字")
    assert mismatch.status_code == 409
    assert mismatch.json()["code"] == "CONFIRM_MISMATCH"

    deleted = test_client.delete(f"/v1/companions/{created['id']}?confirm_name=林夏")
    assert deleted.status_code == 204
    assert test_client.get("/v1/companions").json() == []
    assert test_client.get(f"/v1/companions/{created['id']}").status_code == 404
