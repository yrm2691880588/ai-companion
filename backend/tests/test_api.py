from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def client() -> TestClient:
    # _env_file=None：测试不读取本机 .env，避免真实 Key 影响断言
    return TestClient(create_app(Settings(env="test", _env_file=None)))  # type: ignore[call-arg]


def test_healthz() -> None:
    response = client().get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_registry() -> None:
    payload = client().get("/readyz").json()
    assert payload["status"] == "ok"
    assert payload["providers"] == 9
    assert payload["models"] >= 13


def test_providers_are_listed_with_masked_keys() -> None:
    response = client().get("/v1/model-providers")
    assert response.status_code == 200
    providers = response.json()
    deepseek = next(item for item in providers if item["key"] == "deepseek")
    assert deepseek["scope"] == "system"
    assert deepseek["has_key"] is False
    assert deepseek["masked_key"] == ""
    assert any(model["model_name"] == "deepseek-flash" for model in deepseek["models"])


def test_provider_detail() -> None:
    response = client().get("/v1/model-providers/ollama")
    assert response.status_code == 200
    payload = response.json()
    assert payload["allows_private"] is True
    assert any(model["embedding_dim"] == 1024 for model in payload["models"])


def test_unknown_provider_returns_structured_error() -> None:
    response = client().get("/v1/model-providers/not-exists")
    assert response.status_code == 404
    assert response.json()["code"] == "PROVIDER_NOT_FOUND"


def test_routes_expose_all_tasks() -> None:
    payload = client().get("/v1/model-routes").json()
    tasks = {item["task"] for item in payload}
    assert "chat_main" in tasks
    chat = next(item for item in payload if item["task"] == "chat_main")
    assert chat["chain"][0]["model"] == "deepseek:deepseek-flash"
