"""语音识别与合成接口：上传校验、音频过期、用量记录。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.infra.audio_store import AudioStore
from app.infra.voice.base import Speech, Transcript, VoiceCredential, VoiceOption
from app.infra.voice.registry import VoiceProviderRegistry
from app.main import create_app


class FakeProvider:
    key = "volcengine"
    display_name = "假语音"

    def supports_cloning(self) -> bool:
        return True

    async def list_voices(self, credential: VoiceCredential) -> list[VoiceOption]:
        return [VoiceOption("v1", "音色一")]

    async def transcribe(self, credential, audio, content_type):  # type: ignore[no-untyped-def]
        return Transcript(text="你好呀", duration_ms=800)

    async def synthesize(self, credential, text, voice_id, params=None):  # type: ignore[no-untyped-def]
        return Speech(audio=b"fake-mp3", content_type="audio/mpeg")

    async def probe(self, credential: VoiceCredential) -> dict[str, object]:
        return {"ok": True}


class FailingProvider(FakeProvider):
    async def synthesize(self, credential, text, voice_id, params=None):  # type: ignore[no-untyped-def]
        from app.infra.voice.base import VoiceError

        raise VoiceError("VOICE_TTS_ERROR", "合成失败")


def build(provider: FakeProvider | None = None, tmp_path: Path | None = None) -> TestClient:
    fake = provider or FakeProvider()
    app = create_app(Settings(env="test", _env_file=None))  # type: ignore[call-arg]
    app.state.voice_service._registry = VoiceProviderRegistry({"volcengine": fake})  # type: ignore[attr-defined]
    app.state.audio_store = AudioStore(tmp_path or Path("tmp/test-audio"))
    test_client = TestClient(app)
    test_client.put("/v1/voice/providers/volcengine", json={"app_id": "a", "token": "t"})
    return test_client


def test_transcribe_returns_text(tmp_path: Path) -> None:
    test_client = build(tmp_path=tmp_path)
    response = test_client.post(
        "/v1/voice/transcribe",
        files={"file": ("a.webm", b"audio-bytes", "audio/webm")},
    )
    assert response.status_code == 200
    assert response.json()["text"] == "你好呀"


def test_transcribe_rejects_oversize(tmp_path: Path) -> None:
    test_client = build(tmp_path=tmp_path)
    big = b"x" * (10 * 1024 * 1024 + 1)
    response = test_client.post(
        "/v1/voice/transcribe",
        files={"file": ("a.webm", big, "audio/webm")},
    )
    assert response.status_code == 413


def test_synthesize_returns_url_and_audio_served(tmp_path: Path) -> None:
    test_client = build(tmp_path=tmp_path)
    response = test_client.post(
        "/v1/voice/synthesize",
        json={"text": "你好", "voice_id": "v1"},
    )
    assert response.status_code == 200
    url = response.json()["audio_url"]
    assert url.startswith("/v1/voice/audio/")
    audio = test_client.get(url)
    assert audio.status_code == 200
    assert audio.content == b"fake-mp3"


def test_audio_expired_returns_410(tmp_path: Path) -> None:
    test_client = build(tmp_path=tmp_path)
    response = test_client.get("/v1/voice/audio/deadbeef")
    assert response.status_code == 410


def test_synthesize_failure_propagates(tmp_path: Path) -> None:
    test_client = build(FailingProvider(), tmp_path=tmp_path)
    response = test_client.post("/v1/voice/synthesize", json={"text": "你好", "voice_id": "v1"})
    assert response.status_code == 502
    assert response.json()["code"] == "VOICE_TTS_ERROR"


def test_cleanup_removes_old_files(tmp_path: Path) -> None:
    import os
    import time

    store = AudioStore(tmp_path, ttl_seconds=30)
    audio_id = store.save(b"data")
    path = store.path_for(audio_id)
    assert path is not None
    # 把文件时间戳拨到 10 分钟前，模拟过期
    past = time.time() - 600
    os.utime(path, (past, past))
    assert store.path_for(audio_id) is None
    removed = store.cleanup(max_age_seconds=60)
    assert removed == 1
