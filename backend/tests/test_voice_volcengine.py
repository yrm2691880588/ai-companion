"""火山语音适配：请求构造、错误映射、音色清单。"""

from __future__ import annotations

import base64

import httpx
import pytest

from app.infra.voice.base import VoiceCredential
from app.infra.voice.volcengine import VolcengineVoiceProvider


def credential() -> VoiceCredential:
    return VoiceCredential(app_id="app-1", token="token-1", cluster="volcano_tts")


class FakeResponse:
    def __init__(self, status: int, payload: object = None, content: bytes = b"") -> None:
        self.status_code = status
        self._payload = payload
        self.content = content
        self.headers = {"content-type": "application/json" if payload is not None else "audio/mpeg"}
        self.text = "" if payload is None else str(payload)

    def json(self) -> object:
        return self._payload


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self._response = response
        self.last_url = ""
        self.last_headers: dict[str, str] = {}
        self.last_json: object = None
        self.last_content: bytes = b""

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def post(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json: object = None,
        content: bytes = b"",
        params: dict[str, str] | None = None,
    ) -> FakeResponse:
        self.last_url = url
        self.last_headers = dict(headers or {})
        self.last_json = json
        self.last_content = content
        return self._response


async def test_missing_credential_rejected() -> None:
    provider = VolcengineVoiceProvider()
    with pytest.raises(Exception) as excinfo:
        await provider.list_voices(VoiceCredential())
    assert "VOICE_NO_CREDENTIAL" in str(excinfo.value)


async def test_headers_carry_token() -> None:
    provider = VolcengineVoiceProvider()
    headers = provider._headers(credential())
    assert "token-1" in headers["Authorization"]
    assert headers["Content-Type"] == "application/json"


async def test_app_block_carries_credentials() -> None:
    """火山把凭据放在请求体 app 字段里，不是只放头部。"""
    provider = VolcengineVoiceProvider()
    block = provider._app_block(credential(), "volcano_tts")
    assert block["appid"] == "app-1"
    assert block["token"] == "token-1"
    assert block["cluster"] == "volcano_tts"


async def test_transcribe_parses_text(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        FakeResponse(200, {"result": {"text": " 你好呀 "}, "audio_info": {"duration": 1200}})
    )
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **kwargs: client)
    transcript = await VolcengineVoiceProvider().transcribe(
        credential(), b"fake-audio", "audio/webm"
    )
    assert transcript.text == "你好呀"
    assert transcript.duration_ms == 1200
    assert client.last_url.endswith("/api/v1/asr")


async def test_transcribe_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(FakeResponse(401, {"error": "bad token"}))
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **kwargs: client)
    with pytest.raises(Exception) as excinfo:
        await VolcengineVoiceProvider().transcribe(credential(), b"a", "audio/webm")
    assert "VOICE_AUTH_ERROR" in str(excinfo.value)


async def test_transcribe_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(FakeResponse(429, {}))
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **kwargs: client)
    with pytest.raises(Exception) as excinfo:
        await VolcengineVoiceProvider().transcribe(credential(), b"a", "audio/webm")
    assert "VOICE_RATE_LIMITED" in str(excinfo.value)


async def test_transcribe_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **kwargs: Boom())
    with pytest.raises(Exception) as excinfo:
        await VolcengineVoiceProvider().transcribe(credential(), b"a", "audio/webm")
    assert "VOICE_UNREACHABLE" in str(excinfo.value)


async def test_transcribe_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(FakeResponse(200, {"result": {}}))
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **kwargs: client)
    with pytest.raises(Exception) as excinfo:
        await VolcengineVoiceProvider().transcribe(credential(), b"a", "audio/webm")
    assert "VOICE_ASR_EMPTY" in str(excinfo.value)


async def test_synthesize_returns_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    """火山 /api/v1/tts 返回 JSON，音频在 data 字段的 base64 里。"""
    audio = b"ID3-audio-bytes"
    client = FakeClient(
        FakeResponse(200, {"code": 3000, "data": base64.b64encode(audio).decode()})
    )
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **kwargs: client)
    speech = await VolcengineVoiceProvider().synthesize(
        credential(), "你好", "BV700_streaming", {"speed": 1.5}
    )
    assert speech.audio == audio
    payload = client.last_json
    assert payload["app"]["appid"] == "app-1"
    assert payload["audio"]["voice_type"] == "BV700_streaming"
    assert payload["audio"]["speed_ratio"] == 1.5


async def test_synthesize_base64_json(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = b"mp3-bytes"
    client = FakeClient(FakeResponse(200, {"data": base64.b64encode(raw).decode()}))
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **kwargs: client)
    speech = await VolcengineVoiceProvider().synthesize(credential(), "你好", "BV700_streaming")
    assert speech.audio == raw


async def test_list_voices_returns_builtin() -> None:
    voices = await VolcengineVoiceProvider().list_voices(credential())
    assert len(voices) >= 3
    assert all(voice.voice_id for voice in voices)


async def test_cloning_supported_flag() -> None:
    assert VolcengineVoiceProvider().supports_cloning() is True
