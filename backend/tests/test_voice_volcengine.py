"""火山语音适配：新版控制台 API Key 认证、v3 合成、录音文件识别两步流程。"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from app.infra.voice.base import VoiceCredential
from app.infra.voice.volcengine import (
    DEFAULT_ASR_RESOURCE,
    DEFAULT_TTS_RESOURCE,
    VolcengineVoiceProvider,
)


def credential() -> VoiceCredential:
    return VoiceCredential(app_id="4982965749", token="token-1")


async def _no_sleep(_seconds: float) -> None:
    return None


class FakeStreamResponse:
    """模拟 v3 合成的流式响应：按行返回若干 JSON 块。"""

    def __init__(self, lines: list[dict], status: int = 200) -> None:
        self.status_code = status
        self.reason_phrase = "OK"
        self._lines = lines

    async def __aenter__(self) -> FakeStreamResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def aiter_text(self):  # type: ignore[no-untyped-def]
        for line in self._lines:
            yield json.dumps(line, ensure_ascii=False) + "\n"

    async def aread(self) -> bytes:
        return b""


class FakeClient:
    def __init__(self, *, stream=None, post=None) -> None:  # type: ignore[no-untyped-def]
        self._stream = stream
        self._post = post
        self.last_headers: dict[str, str] = {}
        self.last_json: object = None
        self.calls: list[str] = []

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def stream(self, method: str, url: str, *, headers=None, json=None):  # type: ignore[no-untyped-def]
        self.calls.append(url)
        self.last_headers = dict(headers or {})
        self.last_json = json
        return self._stream

    async def post(self, url: str, *, headers=None, json=None):  # type: ignore[no-untyped-def]
        self.calls.append(url)
        self.last_headers = dict(headers or {})
        self.last_json = json
        return self._post(headers) if self._post else None


def asr_response(status: int, message: str = "OK", payload: dict | None = None):  # type: ignore[no-untyped-def]
    class Resp:
        def __init__(self) -> None:
            self.headers = {"X-Api-Status-Code": str(status), "X-Api-Message": message}
            self.status_code = 200
            self._payload = payload or {}

        def json(self) -> dict:
            return self._payload

    return Resp()


def test_headers_use_api_key_scheme() -> None:
    """新版控制台用 X-Api-* 头，不是旧版 Authorization: Bearer。"""
    headers = VolcengineVoiceProvider()._headers(credential(), resource_id=DEFAULT_TTS_RESOURCE)
    assert headers["X-Api-App-Id"] == "4982965749"
    assert headers["X-Api-Access-Key"] == "token-1"
    assert headers["X-Api-Resource-Id"] == DEFAULT_TTS_RESOURCE
    assert "Authorization" not in headers


def test_missing_credential_rejected() -> None:
    with pytest.raises(Exception) as excinfo:
        VolcengineVoiceProvider()._headers(VoiceCredential(), resource_id="x")
    assert "VOICE_NO_CREDENTIAL" in str(excinfo.value)


def test_default_resources_match_new_console() -> None:
    """默认资源 ID 必须是新版控制台实测可用的那两个。"""
    provider = VolcengineVoiceProvider()
    assert provider._tts_resource == "seed-tts-2.0"
    assert provider._asr_resource == "volc.seedasr.auc"
    assert DEFAULT_TTS_RESOURCE == "seed-tts-2.0"
    assert DEFAULT_ASR_RESOURCE == "volc.seedasr.auc"


async def test_synthesize_concatenates_base64_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    audio_a = b"part-a"
    audio_b = b"part-b"
    client = FakeClient(
        stream=FakeStreamResponse(
            [
                {"code": 0, "data": base64.b64encode(audio_a).decode()},
                {"code": 0, "data": base64.b64encode(audio_b).decode()},
            ]
        )
    )
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **k: client)

    speech = await VolcengineVoiceProvider().synthesize(
        credential(), "你好", "zh_female_vv_uranus_bigtts"
    )
    assert speech.audio == audio_a + audio_b
    assert speech.content_type == "audio/mpeg"
    assert client.last_headers["X-Api-Resource-Id"] == "seed-tts-2.0"
    payload: dict = client.last_json  # type: ignore[assignment]
    assert payload["req_params"]["speaker"] == "zh_female_vv_uranus_bigtts"


async def test_synthesize_maps_missing_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    """资源未开通时给出可操作的中文提示，而不是裸露错误码。"""
    client = FakeClient(
        stream=FakeStreamResponse(
            [{"code": 45000030, "message": "[resource_id=x] requested resource not granted"}]
        )
    )
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **k: client)

    with pytest.raises(Exception) as excinfo:
        await VolcengineVoiceProvider().synthesize(credential(), "你好", "v1")
    assert "VOICE_RESOURCE_NOT_GRANTED" in str(excinfo.value)
    assert "豆包语音合成模型 2.0" in str(excinfo.value)


async def test_synthesize_speed_maps_to_percent(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(stream=FakeStreamResponse([{"code": 0, "data": "AAAA"}]))
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **k: client)

    await VolcengineVoiceProvider().synthesize(credential(), "你好", "v1", {"speed": 1.2})
    payload: dict = client.last_json  # type: ignore[assignment]
    assert payload["req_params"]["audio_params"]["speech_rate"] == 20


async def test_synthesize_empty_chunks_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(stream=FakeStreamResponse([{"code": 0}]))
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **k: client)

    with pytest.raises(Exception) as excinfo:
        await VolcengineVoiceProvider().synthesize(credential(), "你好", "v1")
    assert "VOICE_TTS_EMPTY" in str(excinfo.value)


async def test_transcribe_submits_then_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    """识别必须走 submit + query 两步，不是一次调用。"""
    responses = [
        asr_response(20000000),
        asr_response(20000000, payload={"result": {"text": "你好呀"}}),
    ]
    client = FakeClient(post=lambda headers: responses.pop(0))
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **k: client)
    monkeypatch.setattr("app.infra.voice.volcengine.asyncio.sleep", _no_sleep)

    transcript = await VolcengineVoiceProvider().transcribe(credential(), b"audio", "audio/ogg")
    assert transcript.text == "你好呀"
    assert len(client.calls) == 2
    assert client.calls[0].endswith("/api/v3/auc/bigmodel/submit")
    assert client.calls[1].endswith("/api/v3/auc/bigmodel/query")
    assert client.last_headers["X-Api-Resource-Id"] == "volc.seedasr.auc"


async def test_transcribe_silence_raises_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(post=lambda headers: asr_response(20000003, "silence"))
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **k: client)

    with pytest.raises(Exception) as excinfo:
        await VolcengineVoiceProvider().transcribe(credential(), b"a", "audio/ogg")
    assert "VOICE_ASR_EMPTY" in str(excinfo.value)


async def test_transcribe_missing_asr_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(
        post=lambda headers: asr_response(
            45000030, "[resource_id=x] requested resource not granted"
        )
    )
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **k: client)

    with pytest.raises(Exception) as excinfo:
        await VolcengineVoiceProvider().transcribe(credential(), b"a", "audio/ogg")
    assert "VOICE_RESOURCE_NOT_GRANTED" in str(excinfo.value)
    assert "录音文件识别模型 2.0" in str(excinfo.value)


async def test_transcribe_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient(post=lambda headers: asr_response(20000001, "pending"))
    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **k: client)
    monkeypatch.setattr("app.infra.voice.volcengine.asyncio.sleep", _no_sleep)

    with pytest.raises(Exception) as excinfo:
        await VolcengineVoiceProvider().transcribe(credential(), b"a", "audio/ogg")
    assert "VOICE_ASR_TIMEOUT" in str(excinfo.value)


async def test_list_voices_returns_builtin_2_0_voices() -> None:
    voices = await VolcengineVoiceProvider().list_voices(credential())
    assert len(voices) >= 5
    assert all(voice.voice_id for voice in voices)
    assert any("bigtts" in voice.voice_id or "_tob" in voice.voice_id for voice in voices)


async def test_network_error_becomes_voice_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Boom:
        async def __aenter__(self):  # type: ignore[no-untyped-def]
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def stream(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.infra.voice.volcengine.httpx.AsyncClient", lambda **k: Boom())
    with pytest.raises(Exception) as excinfo:
        await VolcengineVoiceProvider().synthesize(credential(), "你好", "v1")
    assert "VOICE_UNREACHABLE" in str(excinfo.value)
