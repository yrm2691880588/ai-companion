"""本地供应商配置：保存 Key/Base URL/启用，并热更新注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.errors import InvalidInput, NotFound
from app.security.crypto import SecretBox


@dataclass(slots=True)
class ProviderSetting:
    provider_key: str
    api_key: str = ""
    base_url: str | None = None
    enabled: bool = True


class ProviderSettingsRepository(Protocol):
    async def all(self) -> dict[str, ProviderSetting]: ...

    async def upsert(self, setting: ProviderSetting) -> ProviderSetting: ...


class InMemoryProviderSettingsRepository:
    def __init__(self) -> None:
        self._items: dict[str, ProviderSetting] = {}

    async def all(self) -> dict[str, ProviderSetting]:
        return dict(self._items)

    async def upsert(self, setting: ProviderSetting) -> ProviderSetting:
        self._items[setting.provider_key] = setting
        return setting


class ProviderSettingsService:
    def __init__(
        self,
        repo: ProviderSettingsRepository,
        *,
        box: SecretBox | None = None,
        known_providers: set[str] | None = None,
    ) -> None:
        self._repo = repo
        self._box = box
        self._known = known_providers or set()

    async def load(self) -> dict[str, ProviderSetting]:
        return await self._repo.all()

    async def update(
        self,
        provider_key: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        enabled: bool | None = None,
    ) -> ProviderSetting:
        if self._known and provider_key not in self._known:
            raise NotFound("供应商不存在")
        existing = (await self._repo.all()).get(provider_key) or ProviderSetting(
            provider_key=provider_key
        )
        if api_key is not None:
            cleaned = api_key.strip()
            if cleaned and len(cleaned) < 8:
                raise InvalidInput("API Key 太短", code="PROVIDER_KEY_INVALID")
            existing.api_key = cleaned
        if base_url is not None:
            cleaned_url = base_url.strip()
            if cleaned_url and not cleaned_url.startswith(("http://", "https://")):
                raise InvalidInput("Base URL 必须以 http(s):// 开头", code="PROVIDER_URL_INVALID")
            existing.base_url = cleaned_url or None
        if enabled is not None:
            existing.enabled = enabled
        return await self._repo.upsert(existing)

    def keys_for_registry(self, settings: dict[str, ProviderSetting]) -> dict[str, str]:
        """把库里的 Key 解密成注册表可直接使用的映射。"""
        result: dict[str, str] = {}
        for key, setting in settings.items():
            if setting.api_key:
                result[key] = setting.api_key
        return result
