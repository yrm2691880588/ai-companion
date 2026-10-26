"""模型搜索：无 Key 拒绝、上游返回解析、错误映射。"""

from __future__ import annotations

import httpx
import pytest

from app.core.errors import AppError
from app.infra.llm.discovery import ModelDiscovery
from app.infra.llm.types import ProviderConfig


def provider(key: str = "sk-test-123456") -> ProviderConfig:
    return ProviderConfig(
        key="deepseek",
        name="DeepSeek",
        kind="openai",
        base_url="https://api.deepseek.com",
        api_key=key,
    )


class FakeResponse:
    def __init__(self, status: int, payload: object) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> object:
        return self._payload


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self._response = response
        self.requested_url = ""

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, url: str, headers: dict[str, str]) -> FakeResponse:
        self.requested_url = url
        return self._response


async def test_requires_api_key() -> None:
    with pytest.raises(AppError) as excinfo:
        await ModelDiscovery().list_models(provider(""))
    assert excinfo.value.code == "PROVIDER_NO_KEY"


async def test_parses_models_and_sorts(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        FakeResponse(200, {"data": [{"id": "b-model"}, {"id": "a-model"}, {"id": ""}]})
    )
    monkeypatch.setattr("app.infra.llm.discovery.httpx.AsyncClient", lambda **kwargs: client)
    models = await ModelDiscovery().list_models(provider())
    assert [item["id"] for item in models] == ["a-model", "b-model"]
    assert client.requested_url.endswith("/v1/models")


async def test_auth_error_maps_to_400(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(FakeResponse(401, {}))
    monkeypatch.setattr("app.infra.llm.discovery.httpx.AsyncClient", lambda **kwargs: client)
    with pytest.raises(AppError) as excinfo:
        await ModelDiscovery().list_models(provider())
    assert excinfo.value.code == "PROVIDER_AUTH_ERROR"


async def test_unreachable_maps_to_502(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str, headers: dict[str, str]):  # type: ignore[no-untyped-def]
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.infra.llm.discovery.httpx.AsyncClient", lambda **kwargs: Boom())
    with pytest.raises(AppError) as excinfo:
        await ModelDiscovery().list_models(provider())
    assert excinfo.value.code == "PROVIDER_UNREACHABLE"


async def test_bad_payload_maps_to_502(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(FakeResponse(200, {"unexpected": []}))
    monkeypatch.setattr("app.infra.llm.discovery.httpx.AsyncClient", lambda **kwargs: client)
    with pytest.raises(AppError) as excinfo:
        await ModelDiscovery().list_models(provider())
    assert excinfo.value.code == "PROVIDER_BAD_RESPONSE"
