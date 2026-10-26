"""供应商配置：保存 Key、Base URL、启用，以及注册表热更新。"""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.provider_settings import (
    InMemoryProviderSettingsRepository,
    ProviderSettingsService,
)
from app.main import create_app


def client() -> TestClient:
    return TestClient(create_app(Settings(env="test", _env_file=None)))  # type: ignore[call-arg]


def test_list_settings_marks_missing_key() -> None:
    payload = client().get("/v1/provider-settings").json()
    assert len(payload) >= 3
    keys = {item["provider_key"] for item in payload}
    assert "deepseek" in keys
    assert all("has_key" in item for item in payload)
    # 测试环境不读 .env，Key 为空；只校验字段结构，不假设已配置
    assert all(
        item["masked_key"] in ("", "***") or "****" in item["masked_key"] for item in payload
    )


def test_save_key_then_visible_masked() -> None:
    test_client = client()
    response = test_client.patch(
        "/v1/provider-settings/qwen",
        json={"api_key": "sk-test-1234567890"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_key"] is True
    assert "sk-test" not in body["masked_key"]

    listed = test_client.get("/v1/provider-settings").json()
    qwen = next(item for item in listed if item["provider_key"] == "qwen")
    assert qwen["has_key"] is True


def test_save_base_url_and_disable() -> None:
    test_client = client()
    response = test_client.patch(
        "/v1/provider-settings/ollama",
        json={"base_url": "http://127.0.0.1:11434", "enabled": False},
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_invalid_key_and_url_rejected() -> None:
    test_client = client()
    short = test_client.patch("/v1/provider-settings/qwen", json={"api_key": "abc"})
    assert short.status_code == 422
    bad_url = test_client.patch("/v1/provider-settings/qwen", json={"base_url": "ftp://x"})
    assert bad_url.status_code == 422


def test_unknown_provider_rejected() -> None:
    test_client = client()
    response = test_client.patch("/v1/provider-settings/nope", json={"api_key": "sk-1234567890"})
    assert response.status_code == 404


async def test_service_requires_known_provider() -> None:
    service = ProviderSettingsService(
        InMemoryProviderSettingsRepository(), known_providers={"deepseek"}
    )
    setting = await service.update("deepseek", api_key="sk-1234567890")
    assert setting.api_key == "sk-1234567890"
