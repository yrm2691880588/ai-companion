"""语音模块单元测试（按单元测试清单：正常/边界/异常三类）。

重点验证：
- AudioStore 的路径安全与过期
- VoiceService 的入参校验与状态判断
- 服务重启后未预热缓存时的行为
"""

from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.errors import AppError, InvalidInput
from app.domain.voice import (
    InMemoryVoiceSettingsRepository,
    InMemoryVoiceUsageRepository,
    InMemoryVoiceVoiceRepository,
    VoiceService,
    VoiceSetting,
)
from app.infra.audio_store import AudioStore
from app.infra.voice.base import Speech, Transcript, VoiceCredential, VoiceOption
from app.infra.voice.registry import VoiceProviderRegistry

# ---------------- 替身 ----------------


class FakeProvider:
    key = "volcengine"
    display_name = "假语音"

    def __init__(self) -> None:
        self.transcribe_calls = 0
        self.synthesize_calls = 0
        self.last_params: dict[str, object] | None = None

    def supports_cloning(self) -> bool:
        return True

    async def list_voices(self, credential: VoiceCredential) -> list[VoiceOption]:
        return [VoiceOption("v1", "音色一")]

    async def transcribe(self, credential, audio, content_type):  # type: ignore[no-untyped-def]
        self.transcribe_calls += 1
        return Transcript(text="你好", duration_ms=500)

    async def synthesize(self, credential, text, voice_id, params=None):  # type: ignore[no-untyped-def]
        self.synthesize_calls += 1
        self.last_params = params
        return Speech(audio=b"mp3", content_type="audio/mpeg")

    async def probe(self, credential: VoiceCredential) -> dict[str, object]:
        return {"ok": True}


def build_service(
    provider: FakeProvider | None = None,
) -> tuple[VoiceService, FakeProvider, InMemoryVoiceSettingsRepository]:
    fake = provider or FakeProvider()
    repo = InMemoryVoiceSettingsRepository()
    service = VoiceService(
        VoiceProviderRegistry({"volcengine": fake}),
        repo,
        InMemoryVoiceVoiceRepository(),
        InMemoryVoiceUsageRepository(),
    )
    return service, fake, repo


# ---------------- VoiceCredential ----------------


def test_credential_empty_is_not_configured() -> None:
    assert VoiceCredential().configured is False


def test_credential_only_app_id_is_not_configured() -> None:
    assert VoiceCredential(app_id="app-1").configured is False


def test_credential_only_token_is_not_configured() -> None:
    assert VoiceCredential(token="token-1").configured is False


def test_credential_both_fields_is_configured() -> None:
    assert VoiceCredential(app_id="a", token="t").configured is True


# ---------------- VoiceProviderRegistry ----------------


def test_registry_get_unknown_raises() -> None:
    with pytest.raises(KeyError):
        VoiceProviderRegistry({"volcengine": FakeProvider()}).get("nope")


def test_registry_describe_contains_capability() -> None:
    described = VoiceProviderRegistry({"volcengine": FakeProvider()}).describe()
    assert described[0]["key"] == "volcengine"
    assert described[0]["supports_cloning"] is True


def test_registry_keys_lists_providers() -> None:
    assert VoiceProviderRegistry({"volcengine": FakeProvider()}).keys == ["volcengine"]


# ---------------- AudioStore ----------------


def test_audio_store_save_and_load(tmp_path: Path) -> None:
    store = AudioStore(tmp_path, ttl_seconds=60)
    audio_id = store.save(b"hello", suffix=".mp3")
    path = store.path_for(audio_id)
    assert path is not None
    assert path.read_bytes() == b"hello"


def test_audio_store_rejects_path_traversal(tmp_path: Path) -> None:
    store = AudioStore(tmp_path, ttl_seconds=60)
    assert store.path_for("../secret") is None
    assert store.path_for("..\\secret") is None
    assert store.path_for("a/b") is None


def test_audio_store_empty_id_returns_none(tmp_path: Path) -> None:
    store = AudioStore(tmp_path, ttl_seconds=60)
    assert store.path_for("") is None


def test_audio_store_unknown_id_returns_none(tmp_path: Path) -> None:
    store = AudioStore(tmp_path, ttl_seconds=60)
    assert store.path_for("deadbeef") is None


def test_audio_store_expires_after_ttl(tmp_path: Path) -> None:
    store = AudioStore(tmp_path, ttl_seconds=1)
    audio_id = store.save(b"x")
    path = store.path_for(audio_id)
    assert path is not None
    past = time.time() - 10
    import os

    os.utime(path, (past, past))
    assert store.path_for(audio_id) is None


def test_audio_store_cleanup_keeps_fresh_files(tmp_path: Path) -> None:
    store = AudioStore(tmp_path, ttl_seconds=60)
    store.save(b"x")
    assert store.cleanup(max_age_seconds=3600) == 0


def test_audio_store_cleanup_removes_old(tmp_path: Path) -> None:
    import os

    store = AudioStore(tmp_path, ttl_seconds=60)
    audio_id = store.save(b"x")
    path = store.path_for(audio_id)
    assert path is not None
    past = time.time() - 7200
    os.utime(path, (past, past))
    assert store.cleanup(max_age_seconds=3600) == 1


def test_audio_store_ids_are_unique(tmp_path: Path) -> None:
    store = AudioStore(tmp_path, ttl_seconds=60)
    ids = {store.save(b"x") for _ in range(20)}
    assert len(ids) == 20


# ---------------- VoiceService：配置状态 ----------------


async def test_transcribe_before_config_raises() -> None:
    service, fake, _ = build_service()
    await service.load()
    with pytest.raises(AppError) as excinfo:
        await service.transcribe("volcengine", b"audio", "audio/webm", user_id="u1")
    assert excinfo.value.code == "VOICE_NOT_CONFIGURED"
    assert fake.transcribe_calls == 0


async def test_transcribe_without_load_raises() -> None:
    """服务刚启动、尚未 load() 时也不能崩，应给出明确错误。"""
    service, _, _ = build_service()
    with pytest.raises(AppError) as excinfo:
        await service.transcribe("volcengine", b"audio", "audio/webm", user_id="u1")
    assert excinfo.value.code == "VOICE_NOT_CONFIGURED"


async def test_transcribe_when_disabled_raises() -> None:
    service, _, repo = build_service()
    await repo.upsert(
        VoiceSetting(
            provider_key="volcengine",
            credential=VoiceCredential(app_id="a", token="t"),
            enabled=False,
        )
    )
    await service.load()
    with pytest.raises(AppError) as excinfo:
        await service.transcribe("volcengine", b"audio", "audio/webm", user_id="u1")
    assert excinfo.value.code == "VOICE_DISABLED"


async def test_transcribe_unknown_provider_raises_not_found() -> None:
    service, _, _ = build_service()
    await service.load()
    with pytest.raises(AppError) as excinfo:
        await service.transcribe("nope", b"audio", "audio/webm", user_id="u1")
    assert excinfo.value.code == "NOT_FOUND"


# ---------------- VoiceService：入参边界 ----------------


async def test_transcribe_empty_audio_rejected() -> None:
    service, _, repo = build_service()
    await repo.upsert(
        VoiceSetting(provider_key="volcengine", credential=VoiceCredential(app_id="a", token="t"))
    )
    await service.load()
    with pytest.raises(InvalidInput):
        await service.transcribe("volcengine", b"", "audio/webm", user_id="u1")


async def test_transcribe_oversize_audio_rejected() -> None:
    service, fake, repo = build_service()
    await repo.upsert(
        VoiceSetting(provider_key="volcengine", credential=VoiceCredential(app_id="a", token="t"))
    )
    await service.load()
    big = b"x" * (10 * 1024 * 1024 + 1)
    with pytest.raises(AppError) as excinfo:
        await service.transcribe("volcengine", big, "audio/webm", user_id="u1")
    assert excinfo.value.code == "VOICE_AUDIO_TOO_LARGE"
    assert fake.transcribe_calls == 0


async def test_synthesize_empty_text_rejected() -> None:
    service, _, repo = build_service()
    await repo.upsert(
        VoiceSetting(provider_key="volcengine", credential=VoiceCredential(app_id="a", token="t"))
    )
    await service.load()
    with pytest.raises(InvalidInput):
        await service.synthesize("volcengine", "   ", "v1", user_id="u1")


async def test_synthesize_text_too_long_rejected() -> None:
    service, _, repo = build_service()
    await repo.upsert(
        VoiceSetting(provider_key="volcengine", credential=VoiceCredential(app_id="a", token="t"))
    )
    await service.load()
    with pytest.raises(InvalidInput):
        await service.synthesize("volcengine", "字" * 2001, "v1", user_id="u1")


async def test_synthesize_passes_params_to_provider() -> None:
    service, fake, repo = build_service()
    await repo.upsert(
        VoiceSetting(provider_key="volcengine", credential=VoiceCredential(app_id="a", token="t"))
    )
    await service.load()
    await service.synthesize("volcengine", "你好", "v1", {"speed": 20}, user_id="u1")
    assert fake.last_params == {"speed": 20}


# ---------------- VoiceService：成本估算 ----------------


def test_estimate_cost_zero_chars() -> None:
    assert VoiceService._estimate_cost(0) == Decimal("0.000000")


def test_estimate_cost_one_thousand_chars() -> None:
    assert VoiceService._estimate_cost(1000) == Decimal("0.100000")


def test_estimate_cost_rounds_to_six_decimals() -> None:
    cost = VoiceService._estimate_cost(1)
    assert cost == Decimal("0.000100")
    assert cost.as_tuple().exponent == -6


# ---------------- VoiceService：用量与负值 ----------------


async def test_transcribe_writes_usage() -> None:
    service, _, repo = build_service()
    usage = InMemoryVoiceUsageRepository()
    service._usage = usage  # type: ignore[attr-defined]
    await repo.upsert(
        VoiceSetting(provider_key="volcengine", credential=VoiceCredential(app_id="a", token="t"))
    )
    await service.load()
    await service.transcribe("volcengine", b"audio", "audio/webm", user_id="u1")
    assert len(usage.records) == 1
    assert usage.records[0].asr_ms == 500
    assert usage.records[0].status == "ok"


async def test_synthesize_writes_usage_with_cost() -> None:
    service, _, repo = build_service()
    usage = InMemoryVoiceUsageRepository()
    service._usage = usage  # type: ignore[attr-defined]
    await repo.upsert(
        VoiceSetting(provider_key="volcengine", credential=VoiceCredential(app_id="a", token="t"))
    )
    await service.load()
    await service.synthesize("volcengine", "你好世界", "v1", user_id="u1")
    assert len(usage.records) == 1
    assert usage.records[0].tts_chars == 4
    assert usage.records[0].cost_cny == Decimal("0.000400")
