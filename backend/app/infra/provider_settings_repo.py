"""供应商配置仓储：Key 用主密钥加密后落库。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.provider_settings import ProviderSetting
from app.models.provider_settings import ProviderSettingRow
from app.security.crypto import SecretBox


class SqlProviderSettingsRepository:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], box: SecretBox | None
    ) -> None:
        self._session_factory = session_factory
        self._box = box

    async def all(self) -> dict[str, ProviderSetting]:
        async with self._session_factory() as session:
            rows = (await session.execute(select(ProviderSettingRow))).scalars().all()
        result: dict[str, ProviderSetting] = {}
        for row in rows:
            api_key = ""
            if row.api_key_enc and self._box is not None:
                try:
                    api_key = self._box.decrypt(row.api_key_enc)
                except Exception:
                    api_key = ""
            result[row.provider_key] = ProviderSetting(
                provider_key=row.provider_key,
                api_key=api_key,
                base_url=row.base_url,
                enabled=row.enabled,
            )
        return result

    async def upsert(self, setting: ProviderSetting) -> ProviderSetting:
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(ProviderSettingRow).where(
                        ProviderSettingRow.provider_key == setting.provider_key
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = ProviderSettingRow(provider_key=setting.provider_key)
                session.add(row)
            row.api_key_enc = (
                self._box.encrypt(setting.api_key) if setting.api_key and self._box else None
            )
            row.base_url = setting.base_url
            row.enabled = setting.enabled
            await session.commit()
        return setting
