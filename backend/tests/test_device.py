"""设备标识：请求头写入、默认回退、超长截断。"""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.device import LOCAL_DEVICE, current_device_id, device_scope
from app.domain.companions import InMemoryCompanionRepository, LLMResult
from app.domain.templates import TEMPLATES, InMemoryTemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import Usage
from app.main import create_app

PERSONA = {
    "name": "设备测试",
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


def test_default_device_is_local() -> None:
    assert current_device_id() == LOCAL_DEVICE


def test_device_scope_sets_and_restores() -> None:
    with device_scope("01ABC"):
        assert current_device_id() == "01ABC"
    assert current_device_id() == LOCAL_DEVICE


def test_device_scope_empty_falls_back() -> None:
    with device_scope(""):
        assert current_device_id() == LOCAL_DEVICE


def test_device_scope_truncates_long_value() -> None:
    with device_scope("x" * 200):
        assert len(current_device_id()) == 64


def test_request_header_sets_device() -> None:
    """请求带 X-Device-Id 时，处理期间能读到该值。"""
    test_client = client()
    response = test_client.get("/v1/device/whoami", headers={"X-Device-Id": "01TEST"})
    assert response.status_code == 200
    assert response.json()["device_id"] == "01TEST"


def test_request_without_header_reports_local() -> None:
    test_client = client()
    response = test_client.get("/v1/device/whoami")
    assert response.json()["device_id"] == LOCAL_DEVICE
