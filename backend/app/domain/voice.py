"""语音：供应商配置、音色缓存、识别与合成编排。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from app.core.errors import AppError, InvalidInput, NotFound
from app.infra.voice.base import (
    Speech,
    Transcript,
    VoiceCredential,
    VoiceOption,
    VoiceProvider,
)
from app.infra.voice.registry import VoiceProviderRegistry
from app.security.crypto import SecretBox

VOICE_CACHE_HOURS = 24


@dataclass(slots=True)
class VoiceSetting:
    provider_key: str
    credential: VoiceCredential = field(default_factory=VoiceCredential)
    base_url: str | None = None
    enabled: bool = True


@dataclass(slots=True)
class VoiceUsageRecord:
    user_id: str
    provider_key: str
    session_id: int | None = None
    asr_ms: int | None = None
    tts_chars: int | None = None
    cost_cny: Decimal | None = None
    status: str = "ok"


class VoiceSettingsRepository(Protocol):
    async def all(self) -> dict[str, VoiceSetting]: ...

    async def upsert(self, setting: VoiceSetting) -> VoiceSetting: ...


class VoiceVoiceRepository(Protocol):
    async def list(self, provider_key: str) -> tuple[list[VoiceOption], datetime | None]: ...

    async def replace(self, provider_key: str, voices: list[VoiceOption]) -> None: ...


class VoiceUsageRepository(Protocol):
    async def add(self, record: VoiceUsageRecord) -> None: ...


class InMemoryVoiceSettingsRepository:
    def __init__(self) -> None:
        self._items: dict[str, VoiceSetting] = {}

    async def all(self) -> dict[str, VoiceSetting]:
        return dict(self._items)

    async def upsert(self, setting: VoiceSetting) -> VoiceSetting:
        self._items[setting.provider_key] = setting
        return setting


class InMemoryVoiceVoiceRepository:
    def __init__(self) -> None:
        self._items: dict[str, tuple[list[VoiceOption], datetime]] = {}

    async def list(self, provider_key: str) -> tuple[list[VoiceOption], datetime | None]:
        cached = self._items.get(provider_key)
        if cached is None:
            return [], None
        return cached[0], cached[1]

    async def replace(self, provider_key: str, voices: list[VoiceOption]) -> None:
        self._items[provider_key] = (voices, datetime.now(UTC))


class InMemoryVoiceUsageRepository:
    def __init__(self) -> None:
        self.records: list[VoiceUsageRecord] = []

    async def add(self, record: VoiceUsageRecord) -> None:
        self.records.append(record)


class VoiceService:
    def __init__(
        self,
        registry: VoiceProviderRegistry,
        settings: VoiceSettingsRepository,
        voices: VoiceVoiceRepository,
        usage: VoiceUsageRepository,
        *,
        box: SecretBox | None = None,
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._voices = voices
        self._usage = usage
        self._box = box
        self._cached: dict[str, VoiceSetting] = {}

    # ---------- 配置 ----------
    async def load(self) -> dict[str, VoiceSetting]:
        self._cached = await self._settings.all()
        return dict(self._cached)

    async def list_providers(self) -> list[dict[str, object]]:
        stored = self._cached or await self.load()
        result: list[dict[str, object]] = []
        for item in self._registry.describe():
            key = str(item["key"])
            setting = stored.get(key)
            result.append(
                {
                    **item,
                    "configured": bool(setting and setting.credential.configured),
                    "enabled": setting.enabled if setting else True,
                    "app_id": setting.credential.app_id if setting else "",
                }
            )
        return result

    async def update(
        self,
        provider_key: str,
        *,
        app_id: str | None = None,
        token: str | None = None,
        cluster: str | None = None,
        base_url: str | None = None,
        enabled: bool | None = None,
    ) -> VoiceSetting:
        self._provider_or_404(provider_key)
        stored = self._cached or await self.load()
        existing = stored.get(provider_key) or VoiceSetting(provider_key=provider_key)
        if app_id is not None:
            existing.credential.app_id = app_id.strip()
        if token is not None:
            existing.credential.token = token.strip()
        if cluster is not None:
            existing.credential.cluster = cluster.strip()
        if base_url is not None:
            cleaned = base_url.strip()
            if cleaned and not cleaned.startswith(("http://", "https://")):
                raise InvalidInput("Base URL 必须以 http(s):// 开头", code="VOICE_URL_INVALID")
            existing.base_url = cleaned or None
        if enabled is not None:
            existing.enabled = enabled
        saved = await self._settings.upsert(existing)
        self._cached[provider_key] = saved
        # 供应商换了地址时重建适配器
        if base_url is not None and provider_key == "volcengine":
            from app.infra.voice.volcengine import VolcengineVoiceProvider

            self._registry = VoiceProviderRegistry(
                {
                    **{k: self._registry.get(k) for k in self._registry.keys},
                    provider_key: VolcengineVoiceProvider(base_url=existing.base_url),
                }
            )
        return saved

    def _provider_or_404(self, provider_key: str) -> VoiceProvider:
        try:
            return self._registry.get(provider_key)
        except KeyError as exc:
            raise NotFound("语音供应商不存在") from exc

    def _credential(self, provider_key: str) -> tuple[VoiceProvider, VoiceCredential]:
        provider = self._provider_or_404(provider_key)
        setting = self._cached.get(provider_key)
        if setting is None or not setting.credential.configured:
            raise AppError(
                code="VOICE_NOT_CONFIGURED",
                message="请先在「模型与用量 → 语音」里配置 AppID 与 Token",
                status_code=400,
            )
        if not setting.enabled:
            raise AppError(code="VOICE_DISABLED", message="该语音供应商已停用", status_code=400)
        return provider, setting.credential

    # ---------- 音色 ----------
    async def list_voices(self, provider_key: str, *, refresh: bool = False) -> list[VoiceOption]:
        provider, credential = self._credential(provider_key)
        cached, cached_at = await self._voices.list(provider_key)
        fresh = cached_at is not None and datetime.now(UTC) - cached_at < timedelta(
            hours=VOICE_CACHE_HOURS
        )
        if cached and fresh and not refresh:
            return cached
        voices = await provider.list_voices(credential)
        if voices:
            await self._voices.replace(provider_key, voices)
        return voices

    async def probe(self, provider_key: str) -> dict[str, object]:
        provider, credential = self._credential(provider_key)
        return await provider.probe(credential)

    # ---------- 识别与合成 ----------
    async def transcribe(
        self, provider_key: str, audio: bytes, content_type: str, *, user_id: str
    ) -> Transcript:
        provider, credential = self._credential(provider_key)
        if not audio:
            raise InvalidInput("音频为空", code="VOICE_EMPTY_AUDIO")
        if len(audio) > 10 * 1024 * 1024:
            raise AppError(code="VOICE_AUDIO_TOO_LARGE", message="音频超过 10MB", status_code=413)
        result = await provider.transcribe(credential, audio, content_type)
        await self._usage.add(
            VoiceUsageRecord(
                user_id=user_id,
                provider_key=provider_key,
                asr_ms=result.duration_ms,
                status="ok",
            )
        )
        return result

    async def synthesize(
        self,
        provider_key: str,
        text: str,
        voice_id: str,
        params: dict[str, object] | None = None,
        *,
        user_id: str,
        session_id: int | None = None,
    ) -> Speech:
        provider, credential = self._credential(provider_key)
        cleaned = text.strip()
        if not cleaned:
            raise InvalidInput("待合成文本为空", code="VOICE_EMPTY_TEXT")
        if len(cleaned) > 2000:
            raise InvalidInput("单次合成不超过 2000 字", code="VOICE_TEXT_TOO_LONG")
        speech = await provider.synthesize(credential, cleaned, voice_id, params or {})
        await self._usage.add(
            VoiceUsageRecord(
                user_id=user_id,
                provider_key=provider_key,
                session_id=session_id,
                tts_chars=len(cleaned),
                cost_cny=self._estimate_cost(len(cleaned)),
                status="ok",
            )
        )
        return speech

    @staticmethod
    def _estimate_cost(chars: int) -> Decimal:
        """粗估：火山 TTS 约 0.1 元/千字；仅作提示，不是账单。"""
        return (Decimal(chars) / Decimal(1000) * Decimal("0.1")).quantize(Decimal("0.000001"))

    # ---------- 序列化 ----------
    def dump_credential(self, setting: VoiceSetting) -> str:
        if self._box is None:
            raise AppError(
                code="VOICE_NO_MASTER_KEY", message="缺少主密钥，无法加密保存", status_code=500
            )
        return self._box.encrypt(json.dumps(setting.credential.__dict__, ensure_ascii=False))

    def load_credential(self, cipher: str | None) -> VoiceCredential:
        if not cipher or self._box is None:
            return VoiceCredential()
        try:
            data = json.loads(self._box.decrypt(cipher))
        except Exception:
            return VoiceCredential()
        return VoiceCredential(
            app_id=str(data.get("app_id", "")),
            token=str(data.get("token", "")),
            cluster=str(data.get("cluster", "")),
        )
