"""数据导入：按 ULID 去重、重复跳过、格式校验。"""

from __future__ import annotations

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
    "identity": "测试角色",
    "gender": "不设定",
    "age": 25,
    "personality": ["安静", "可靠"],
    "speaking_style": "句子短，语气平稳。",
    "background": "仅用于自动化测试的临时角色。",
    "tags": ["测试"],
    "relationship": "测试关系",
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


def import_body(*ulids: str) -> dict:
    return {
        "format": "ai-companion-export",
        "version": 2,
        "companions": [
            {"ulid": ulid, "name": PERSONA["name"], "persona": PERSONA} for ulid in ulids
        ],
    }


def test_import_creates_when_absent() -> None:
    test_client = client()
    response = test_client.post("/v1/me/import", json=import_body("01AAAAAAAAAAAAAAAAAAAAAAAA"))
    assert response.status_code == 200
    report = response.json()
    assert report["created"] == ["01AAAAAAAAAAAAAAAAAAAAAAAA"]
    assert report["skipped"] == []
    assert report["failed"] == []


def test_import_skips_existing_ulid() -> None:
    test_client = client()
    body = import_body("01BBBBBBBBBBBBBBBBBBBBBBBB")
    first = test_client.post("/v1/me/import", json=body).json()
    assert len(first["created"]) == 1
    assert first["created"][0] == "01BBBBBBBBBBBBBBBBBBBBBBBB"
    assert len(test_client.get("/v1/companions").json()) == 1

    second = test_client.post("/v1/me/import", json=body).json()
    assert second["created"] == []
    assert second["skipped"] == ["01BBBBBBBBBBBBBBBBBBBBBBBB"]
    assert len(test_client.get("/v1/companions").json()) == 1


def test_import_does_not_overwrite_existing() -> None:
    """重复导入不能改动已有伴侣的人设。"""
    test_client = client()
    body = import_body("01CCCCCCCCCCCCCCCCCCCCCCCC")
    test_client.post("/v1/me/import", json=body)

    changed = import_body("01CCCCCCCCCCCCCCCCCCCCCCCC")
    changed["companions"][0]["persona"] = {**PERSONA, "name": "改过的名字"}
    report = test_client.post("/v1/me/import", json=changed).json()

    assert report["skipped"] == ["01CCCCCCCCCCCCCCCCCCCCCCCC"]
    companions = test_client.get("/v1/companions").json()
    assert len(companions) == 1
    assert companions[0]["persona"]["name"] == "导入测试"


def test_import_rejects_wrong_format() -> None:
    test_client = client()
    response = test_client.post(
        "/v1/me/import",
        json={"format": "something-else", "version": 2, "companions": []},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "IMPORT_FORMAT"


def test_import_rejects_future_version() -> None:
    test_client = client()
    response = test_client.post(
        "/v1/me/import",
        json={"format": "ai-companion-export", "version": 99, "companions": []},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "IMPORT_VERSION"


def test_import_reports_item_failure_without_aborting() -> None:
    """一条坏数据不能让整包失败。"""
    test_client = client()
    body = import_body("01DDDDDDDDDDDDDDDDDDDDDDDD")
    body["companions"].append({"ulid": "01EEEEEEEEEEEEEEEEEEEEEEEE", "persona": {}})
    report = test_client.post("/v1/me/import", json=body).json()
    assert len(report["created"]) == 1
    assert len(report["failed"]) == 1
    assert report["failed"][0]["index"] == "1"


def test_import_without_ulid_still_creates() -> None:
    test_client = client()
    body = {"format": "ai-companion-export", "version": 2, "companions": [{"persona": PERSONA}]}
    report = test_client.post("/v1/me/import", json=body).json()
    assert len(report["created"]) == 1


def test_import_preview_documents_rules() -> None:
    body = client().get("/v1/me/import/preview").json()
    assert body["dedupe"] == "companion-ulid"
    assert body["conflict"] == "skip-and-report"
