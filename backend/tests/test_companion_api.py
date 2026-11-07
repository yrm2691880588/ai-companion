import json
from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.usage import CallContext
from app.infra.llm.types import Message, TaskName, Usage
from app.main import create_app

PERSONA_DICT = {
    "name": "林夏",
    "identity": "心理学研究生",
    "gender": "女",
    "age": 24,
    "personality": ["温柔", "偶尔毒舌", "共情力强"],
    "speaking_style": "句子短，口语化，先共情再给建议，偶尔用反问。",
    "background": "在读心理学研究生，晚上在便利店做兼职，见过很多深夜的人。",
    "tags": ["温柔", "毒舌学姐", "夜猫子"],
    "relationship": "住在隔壁的学姐",
    "example_openers": ["今天怎么这么晚才回来？"],
}


class FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def complete(
        self, task: TaskName, messages: list[Message], *, context: CallContext
    ) -> LLMResult:
        self.calls += 1
        return LLMResult(
            text=self.responses.pop(0),
            model_key="fake:model",
            usage=Usage(prompt_tokens=10, completion_tokens=10),
            cost_cny=Decimal("0.0001"),
        )


def client(llm: FakeLLM) -> TestClient:
    app = create_app(
        Settings(env="test", _env_file=None),  # type: ignore[call-arg]
        companion_repo=InMemoryCompanionRepository(),
        llm_client=llm,
    )
    return TestClient(app)


def test_persona_schema_endpoint() -> None:
    response = client(FakeLLM([])).get("/v1/personas/schema")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert len(payload["dimensions"]) == 10
    keys = [item["key"] for item in payload["dimensions"]]
    assert keys[0] == "name"
    assert "speaking_style" in keys


def test_draft_endpoint_generates_persona() -> None:
    response = client(FakeLLM([json.dumps(PERSONA_DICT, ensure_ascii=False)])).post(
        "/v1/personas/draft", json={"description": "想要一个温柔但偶尔毒舌的心理学学姐"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["persona"]["name"] == "林夏"
    assert payload["model_key"] == "fake:model"
    assert payload["cost_cny"] == 0.0001


def test_refine_endpoint_returns_suggestion_without_saving() -> None:
    """草稿单维改写：不创建任何伴侣，只返回建议值。"""
    test_client = client(
        FakeLLM([json.dumps({"value": "句子更短、更冷，常用短句收尾"}, ensure_ascii=False)])
    )
    response = test_client.post(
        "/v1/personas/refine",
        json={
            "persona": PERSONA_DICT,
            "dimension": "speaking_style",
            "hint": "再冷一点、短一点",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["dimension"] == "speaking_style"
    assert payload["value"].startswith("句子更短")
    assert payload["model_key"] == "fake:model"
    # 关键：没有创建伴侣
    assert test_client.get("/v1/companions").json() == []


def test_refine_endpoint_rejects_identity_dimension() -> None:
    test_client = client(FakeLLM([]))
    response = test_client.post(
        "/v1/personas/refine",
        json={"persona": PERSONA_DICT, "dimension": "name", "hint": "换个名字"},
    )
    # 项目里 InvalidInput 统一映射 422（不是 400）
    assert response.status_code == 422
    assert response.json()["code"] == "DIMENSION_NOT_REFINABLE"


def test_refine_endpoint_rejects_bad_dimension_value() -> None:
    """模型给出不合法值时要报错，而不是把坏数据交给前端。"""
    test_client = client(FakeLLM([json.dumps({"value": "短"}, ensure_ascii=False)]))
    response = test_client.post(
        "/v1/personas/refine",
        json={"persona": PERSONA_DICT, "dimension": "background", "hint": None},
    )
    assert response.status_code == 502
    assert response.json()["code"] == "PERSONA_GENERATION_FAILED"


def test_create_list_and_get_companion() -> None:
    test_client = client(FakeLLM([]))
    created = test_client.post("/v1/companions", json={"persona": PERSONA_DICT})
    assert created.status_code == 201
    companion = created.json()
    assert companion["current_version"] == 1
    assert companion["name"] == "林夏"

    listed = test_client.get("/v1/companions").json()
    assert len(listed) == 1
    assert listed[0]["id"] == companion["id"]

    detail = test_client.get(f"/v1/companions/{companion['id']}")
    assert detail.status_code == 200
    assert detail.json()["persona"]["tags"] == PERSONA_DICT["tags"]


def test_patch_dimension_creates_new_version() -> None:
    test_client = client(FakeLLM([]))
    companion = test_client.post("/v1/companions", json={"persona": PERSONA_DICT}).json()
    patched = test_client.patch(
        f"/v1/companions/{companion['id']}/persona",
        json={"dimension": "speaking_style", "value": "句子更短，偶尔用表情。"},
    )
    assert patched.status_code == 200
    payload = patched.json()
    assert payload["current_version"] == 2
    assert payload["persona"]["speaking_style"] == "句子更短，偶尔用表情。"


def test_patch_invalid_value_returns_422() -> None:
    test_client = client(FakeLLM([]))
    companion = test_client.post("/v1/companions", json={"persona": PERSONA_DICT}).json()
    patched = test_client.patch(
        f"/v1/companions/{companion['id']}/persona",
        json={"dimension": "age", "value": 10},
    )
    assert patched.status_code == 422
    assert patched.json()["code"] == "PERSONA_INVALID"


def test_regenerate_returns_suggested_value() -> None:
    test_client = client(FakeLLM([json.dumps({"value": "句子更短更冷"})]))
    companion = test_client.post("/v1/companions", json={"persona": PERSONA_DICT}).json()
    response = test_client.post(
        f"/v1/companions/{companion['id']}/persona/regenerate",
        json={"dimension": "speaking_style", "hint": "再冷一点"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["value"] == "句子更短更冷"
    assert payload["model_key"] == "fake:model"


def test_unknown_companion_returns_404_with_code() -> None:
    response = client(FakeLLM([])).get("/v1/companions/999")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_rejects_too_many_companions() -> None:
    test_client = client(FakeLLM([]))
    from app.domain.companions import MAX_COMPANIONS

    for _ in range(MAX_COMPANIONS):
        assert test_client.post("/v1/companions", json={"persona": PERSONA_DICT}).status_code == 201
    response = test_client.post("/v1/companions", json={"persona": PERSONA_DICT})
    assert response.status_code == 409
    assert response.json()["code"] == "COMPANION_LIMIT"


def test_persona_version_endpoints() -> None:
    """版本列表 + 还原：还原后版本号递增，历史不丢。"""
    test_client = client(FakeLLM([]))
    created = test_client.post("/v1/companions", json={"persona": PERSONA_DICT}).json()
    cid = created["id"]

    # 创建即 v1
    listed = test_client.get(f"/v1/companions/{cid}/personas")
    assert listed.status_code == 200
    assert [v["version"] for v in listed.json()] == [1]

    # 保存一次 → v2
    changed = dict(PERSONA_DICT)
    changed["speaking_style"] = "更冷更短，一次不超过十个字。"
    saved = test_client.put(f"/v1/companions/{cid}/persona", json={"persona": changed})
    assert saved.status_code == 200
    assert saved.json()["current_version"] == 2

    listed = test_client.get(f"/v1/companions/{cid}/personas").json()
    assert [v["version"] for v in listed] == [2, 1]

    # 还原到 v1 → 变成 v3，内容回到最初
    restored = test_client.post(f"/v1/companions/{cid}/personas/1/restore")
    assert restored.status_code == 200
    assert restored.json()["current_version"] == 3
    assert restored.json()["persona"]["speaking_style"] == PERSONA_DICT["speaking_style"]

    listed = test_client.get(f"/v1/companions/{cid}/personas").json()
    assert [v["version"] for v in listed] == [3, 2, 1]


def test_restore_missing_version_returns_404() -> None:
    test_client = client(FakeLLM([]))
    created = test_client.post("/v1/companions", json={"persona": PERSONA_DICT}).json()
    response = test_client.post(f"/v1/companions/{created['id']}/personas/99/restore")
    assert response.status_code == 404


# 归属隔离不在这里测：测试环境是「本地单用户模式」，
# X-User-Id 头会被忽略（所有人都是 local-user），
# 用请求头造不出第二个用户。归属校验在服务层测（test_companion_service.py
# 的 test_versions_are_isolated_per_user），那才是真正执行检查的地方。
