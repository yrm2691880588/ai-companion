"""批量删除：确认词、上限、去重、部分失败隔离。"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.companions import BATCH_DELETE_CONFIRM as BATCH_CONFIRM_PHRASE
from app.domain.companions import MAX_BATCH_DELETE as MAX_BATCH
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.deletion import DeletionService
from app.domain.templates import TEMPLATES, InMemoryTemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import Usage
from app.main import create_app

PERSONA = {
    "name": "批量测试",
    "identity": "测试角色",
    "gender": "不设定",
    "age": 25,
    "personality": ["安静", "可靠"],
    "speaking_style": "句子短，语气平稳。",
    "background": "仅用于自动化测试的临时角色，不涉及真实人物。",
    "tags": ["测试"],
    "relationship": "测试关系",
}


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


class FakeDeletion(DeletionService):
    """删除任务桩：只记录，不真的清库。

    继承真实类型是为了通过 deps 里的 isinstance 检查；
    真实实现依赖数据库仓储，测试环境没有它。
    """

    def __init__(self) -> None:  # 不调用父类 __init__，避免要求仓储
        self.enqueued: list[tuple[str, int]] = []

    async def enqueue(self, user_id: str, companion_id: int):  # type: ignore[override]
        self.enqueued.append((user_id, companion_id))
        job_id = len(self.enqueued)

        class Job:
            id = job_id

        return Job()

    async def run_job(self, job_id: int) -> dict[str, int]:  # type: ignore[override]
        return {}


@pytest.fixture()
def deletion() -> FakeDeletion:
    return FakeDeletion()


@pytest.fixture()
def client(deletion: FakeDeletion) -> TestClient:
    app = create_app(
        Settings(env="test", _env_file=None),  # type: ignore[call-arg]
        companion_repo=InMemoryCompanionRepository(),
        template_repo=InMemoryTemplateRepository(TEMPLATES),
        llm_client=FakeLLM(),
    )
    # create_app 内部自建 DeletionService（依赖真实数据库仓储），
    # 测试里换成桩，避免后台任务在响应后抛异常。
    app.state.deletion_service = deletion
    return TestClient(app)


def make_companions(client: TestClient, count: int) -> list[int]:
    ids = []
    for index in range(count):
        response = client.post(
            "/v1/companions",
            json={"persona": {**PERSONA, "name": f"测试{index}"}, "name": f"测试{index}"},
        )
        assert response.status_code in (200, 201), response.text
        ids.append(response.json()["id"])
    return ids


def test_confirm_phrase_is_chinese_delete() -> None:
    assert BATCH_CONFIRM_PHRASE == "删除"


def test_batch_delete_requires_confirmation(client: TestClient) -> None:
    ids = make_companions(client, 2)
    response = client.post("/v1/companions/batch-delete", json={"ids": ids, "confirm": "错词"})
    assert response.status_code == 422
    assert response.json()["code"] == "CONFIRM_MISMATCH"
    # 未删除任何伴侣
    assert len(client.get("/v1/companions").json()) == 2


def test_batch_delete_removes_all(client: TestClient) -> None:
    ids = make_companions(client, 3)
    response = client.post(
        "/v1/companions/batch-delete",
        json={"ids": ids, "confirm": BATCH_CONFIRM_PHRASE},
    )
    assert response.status_code == 200
    body = response.json()
    assert sorted(body["deleted"]) == sorted(ids)
    assert body["failed"] == []
    assert client.get("/v1/companions").json() == []


def test_batch_delete_dedupes_ids(client: TestClient) -> None:
    ids = make_companions(client, 1)
    response = client.post(
        "/v1/companions/batch-delete",
        json={"ids": [*ids, *ids], "confirm": BATCH_CONFIRM_PHRASE},
    )
    body = response.json()
    assert body["deleted"] == ids
    assert body["failed"] == []


def test_batch_delete_reports_missing_id(client: TestClient) -> None:
    ids = make_companions(client, 1)
    response = client.post(
        "/v1/companions/batch-delete",
        json={"ids": [*ids, 999999], "confirm": BATCH_CONFIRM_PHRASE},
    )
    body = response.json()
    assert body["deleted"] == ids
    assert len(body["failed"]) == 1
    assert body["failed"][0]["id"] == 999999


def test_batch_delete_rejects_empty_list(client: TestClient) -> None:
    response = client.post(
        "/v1/companions/batch-delete", json={"ids": [], "confirm": BATCH_CONFIRM_PHRASE}
    )
    assert response.status_code == 422


def test_batch_delete_rejects_too_many(client: TestClient) -> None:
    response = client.post(
        "/v1/companions/batch-delete",
        json={"ids": list(range(1, MAX_BATCH + 2)), "confirm": BATCH_CONFIRM_PHRASE},
    )
    assert response.status_code == 422
