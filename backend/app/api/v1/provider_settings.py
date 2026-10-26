"""供应商配置接口：读取状态、保存 Key/Base URL、启用切换。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_id, require_admin
from app.core.errors import AppError
from app.domain.provider_settings import ProviderSettingsService
from app.security.crypto import mask_secret

router = APIRouter(prefix="/v1/provider-settings", tags=["provider-settings"])


class ProviderPatchIn(BaseModel):
    api_key: str | None = Field(default=None, max_length=400)
    base_url: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None


class ProviderSettingOut(BaseModel):
    provider_key: str
    has_key: bool
    masked_key: str
    base_url: str | None = None
    enabled: bool = True


def get_service(request: Request) -> ProviderSettingsService:
    service = getattr(request.app.state, "provider_settings_service", None)
    if not isinstance(service, ProviderSettingsService):
        raise AppError(
            code="PROVIDER_SETTINGS_UNAVAILABLE", message="供应商配置不可用", status_code=503
        )
    return service


ServiceDep = Annotated[ProviderSettingsService, Depends(get_service)]
AdminDep = Annotated[str, Depends(require_admin)]
UserDep = Annotated[str, Depends(get_current_user_id)]


@router.get("", response_model=list[ProviderSettingOut])
async def list_settings(
    request: Request, _admin: AdminDep, service: ServiceDep
) -> list[ProviderSettingOut]:
    stored = await service.load()
    registry = request.app.state.registry
    result: list[ProviderSettingOut] = []
    for key in registry.providers:
        setting = stored.get(key)
        provider = registry.provider(key)
        api_key = setting.api_key if setting and setting.api_key else provider.api_key
        result.append(
            ProviderSettingOut(
                provider_key=key,
                has_key=bool(api_key),
                masked_key=mask_secret(api_key),
                base_url=(setting.base_url if setting and setting.base_url else provider.base_url),
                enabled=setting.enabled if setting else True,
            )
        )
    return result


@router.patch("/{provider_key}", response_model=ProviderSettingOut)
async def update_setting(
    provider_key: str,
    payload: ProviderPatchIn,
    request: Request,
    admin: AdminDep,
    service: ServiceDep,
) -> ProviderSettingOut:
    setting = await service.update(
        provider_key,
        api_key=payload.api_key,
        base_url=payload.base_url,
        enabled=payload.enabled,
    )
    # 热更新注册表：新 Key 立即生效，无需重启
    runtime = request.app.state
    if hasattr(runtime, "apply_provider_settings"):
        await runtime.apply_provider_settings()
    return ProviderSettingOut(
        provider_key=setting.provider_key,
        has_key=bool(setting.api_key),
        masked_key=mask_secret(setting.api_key),
        base_url=setting.base_url,
        enabled=setting.enabled,
    )

