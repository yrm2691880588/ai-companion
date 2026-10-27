"""语音仓储：配置（加密）、音色缓存、用量。"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.voice import VoiceSetting, VoiceUsageRecord
from app.infra.voice.base import VoiceCredential, VoiceOption
from app.models.voice import VoiceProviderSettingRow, VoiceUsageRow, VoiceVoiceRow
from app.security.crypto import SecretBox


class SqlVoiceSettingsRepository:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], box: SecretBox | None
    ) -> None:
        self._session_factory = session_factory
        self._box = box

    def _decrypt(self, cipher: str | None) -> VoiceCredential:
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

    async def all(self) -> dict[str, VoiceSetting]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(VoiceProviderSettingRow))).scalars().all()
        return {
            row.provider_key: VoiceSetting(
                provider_key=row.provider_key,
                credential=self._decrypt(row.credentials_enc),
                base_url=row.base_url,
                enabled=row.enabled,
            )
            for row in rows
        }

    async def upsert(self, setting: VoiceSetting) -> VoiceSetting:
        cipher = None
        if self._box is not None and setting.credential.configured:
            payload = json.dumps(setting.credential.__dict__, ensure_ascii=False)
            cipher = self._box.encrypt(payload)
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(VoiceProviderSettingRow).where(
                        VoiceProviderSettingRow.provider_key == setting.provider_key
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = VoiceProviderSettingRow(provider_key=setting.provider_key)
                session.add(row)
            row.credentials_enc = cipher
            row.base_url = setting.base_url
            row.enabled = setting.enabled
            await session.commit()
        return setting


class SqlVoiceVoiceRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list(self, provider_key: str) -> tuple[list[VoiceOption], datetime | None]:
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(VoiceVoiceRow).where(VoiceVoiceRow.provider_key == provider_key)
                    )
                )
                .scalars()
                .all()
            )
        if not rows:
            return [], None
        options = [
            VoiceOption(
                voice_id=row.voice_id,
                display_name=row.display_name,
                gender=row.gender,
                tags=list(row.tags or []),
                params_schema=dict(row.params_schema or {}),
            )
            for row in rows
        ]
        cached_at = max((row.cached_at for row in rows if row.cached_at), default=None)
        if cached_at is not None and cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=UTC)
        return options, cached_at

    async def replace(self, provider_key: str, voices: list[VoiceOption]) -> None:
        async with self._session_factory() as session:
            await session.execute(
                delete(VoiceVoiceRow).where(VoiceVoiceRow.provider_key == provider_key)
            )
            now = datetime.now(UTC)
            for option in voices:
                session.add(
                    VoiceVoiceRow(
                        provider_key=provider_key,
                        voice_id=option.voice_id,
                        display_name=option.display_name,
                        gender=option.gender,
                        tags=option.tags,
                        params_schema=option.params_schema,
                        cached_at=now,
                    )
                )
            await session.commit()


class SqlVoiceUsageRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, record: VoiceUsageRecord) -> None:
        async with self._session_factory() as session:
            session.add(
                VoiceUsageRow(
                    user_id=record.user_id,
                    session_id=record.session_id,
                    provider_key=record.provider_key,
                    asr_ms=record.asr_ms,
                    tts_chars=record.tts_chars,
                    cost_cny=record.cost_cny,
                    status=record.status,
                )
            )
            await session.commit()
