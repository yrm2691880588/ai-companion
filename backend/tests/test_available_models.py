"""模型下拉只显示可用模型：有 Key 才出现，禁用后消失。"""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def client() -> TestClient:
    return TestClient(create_app(Settings(env="test", _env_file=None)))  # type: ignore[call-arg]


def keys(payload: dict) -> set[str]:
    return {item["key"] for item in payload["models"]}


def test_models_hidden_without_key() -> None:
    test_client = client()
    payload = test_client.get("/v1/admin/settings").json()
    # 测试环境没有任何 Key，可用模型应为空
    assert payload["models"] == []


def test_models_appear_after_key_saved() -> None:
    test_client = client()
    test_client.patch(
        "/v1/provider-settings/deepseek",
        json={"api_key": "sk-test-1234567890"},
    )
    payload = test_client.get("/v1/admin/settings").json()
    assert "deepseek:deepseek-flash" in keys(payload)
    assert "deepseek:deepseek-v4-pro" in keys(payload)


def test_models_disappear_when_disabled() -> None:
    test_client = client()
    test_client.patch(
        "/v1/provider-settings/deepseek",
        json={"api_key": "sk-test-1234567890", "enabled": False},
    )
    payload = test_client.get("/v1/admin/settings").json()
    assert "deepseek:deepseek-flash" not in keys(payload)
