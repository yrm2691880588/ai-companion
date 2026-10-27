"""语音配置接口：保存、探活、音色缓存、错误。"""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.infra.voice.base import VoiceCredential, VoiceOption
from app.infra.voice.registry import VoiceProviderRegistry
from app.main import create_app


class FakeVoiceProvider:
    key = "volcengine"
    display_name = "假语音供应商"

    def __init__(self) -> None:
        self.voice_calls = 0

    def supports_cloning(self) -> bool:
        return True

    async def list_voices(self, credential: VoiceCredential) -> list[VoiceOption]:
        self.voice_calls += 1
        return [
            VoiceOption("v1", "音色一", "女", ["温柔"]),
            VoiceOption("v2", "音色二", "男", ["沉稳"]),
        ]

    async def transcribe(self, credential, audio, content_type):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def synthesize(self, credential, text, voice_id, params=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def probe(self, credential: VoiceCredential) -> dict[str, object]:
        return {"ok": True, "voice_count": 2}


def client(provider: FakeVoiceProvider | None = None) -> tuple[TestClient, FakeVoiceProvider]:
    fake = provider or FakeVoiceProvider()
    app = create_app(Settings(env="test", _env_file=None))  # type: ignore[call-arg]
    app.state.voice_service._registry = VoiceProviderRegistry({"volcengine": fake})  # type: ignore[attr-defined]
    return TestClient(app), fake


def test_list_providers_unconfigured() -> None:
    test_client, _ = client()
    payload = test_client.get("/v1/voice/providers").json()
    assert payload[0]["key"] == "volcengine"
    assert payload[0]["configured"] is False
    assert payload[0]["supports_cloning"] is True


def test_save_credential_then_configured() -> None:
    test_client, _ = client()
    response = test_client.put(
        "/v1/voice/providers/volcengine",
        json={"app_id": "app-1", "token": "token-1", "cluster": "volc_tts"},
    )
    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["app_id"] == "app-1"


def test_voices_require_configuration() -> None:
    test_client, _ = client()
    response = test_client.get("/v1/voice/providers/volcengine/voices")
    assert response.status_code == 400
    assert response.json()["code"] == "VOICE_NOT_CONFIGURED"


def test_voices_cached_until_refresh() -> None:
    test_client, fake = client()
    test_client.put("/v1/voice/providers/volcengine", json={"app_id": "a", "token": "t"})
    first = test_client.get("/v1/voice/providers/volcengine/voices").json()
    second = test_client.get("/v1/voice/providers/volcengine/voices").json()
    assert len(first) == 2
    assert len(second) == 2
    assert fake.voice_calls == 1  # 第二次命中缓存

    test_client.get("/v1/voice/providers/volcengine/voices?refresh=true")
    assert fake.voice_calls == 2


def test_unknown_provider_404() -> None:
    test_client, _ = client()
    response = test_client.put("/v1/voice/providers/nope", json={"app_id": "a"})
    assert response.status_code == 404


def test_invalid_base_url_rejected() -> None:
    test_client, _ = client()
    response = test_client.put("/v1/voice/providers/volcengine", json={"base_url": "ftp://x"})
    assert response.status_code == 422


def test_probe_requires_credential() -> None:
    test_client, _ = client()
    response = test_client.post("/v1/voice/providers/volcengine/probe")
    assert response.status_code == 400
