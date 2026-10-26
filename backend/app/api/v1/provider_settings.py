"""供应商配置接口：读取状态、保存 Key/Base URL、启用切换。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user_id, require_admin
from app.core.errors import AppError
from app.domain.provider_settings import ProviderSettingsService
from app.infra.llm.discovery import ModelDiscovery
from app.infra.llm.pricing import parse_banded_price
from app.infra.llm.registry import ModelRegistry
from app.infra.llm.types import Capability, ModelSpec
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


class DiscoveredModelOut(BaseModel):
    id: str
    owned_by: str = ""


@router.get("/{provider_key}/models", response_model=list[DiscoveredModelOut])
async def discover_models(
    provider_key: str,
    request: Request,
    _admin: AdminDep,
) -> list[DiscoveredModelOut]:
    """向供应商的 /v1/models 拉取真实可用模型。"""
    registry = request.app.state.registry
    try:
        provider = registry.provider(provider_key)
    except KeyError as exc:
        raise AppError(code="PROVIDER_NOT_FOUND", message="供应商不存在", status_code=404) from exc
    models = await ModelDiscovery().list_models(provider)
    return [DiscoveredModelOut(**item) for item in models]


class ImportModelsIn(BaseModel):
    model_ids: list[str] = Field(min_length=1, max_length=200)


@router.post("/{provider_key}/models/import", response_model=list[str])
async def import_models(
    provider_key: str,
    payload: ImportModelsIn,
    request: Request,
    _admin: AdminDep,
) -> list[str]:
    """把搜索到的模型加入本机注册表，随后可在模型下拉里选择。"""
    runtime = request.app.state
    registry: ModelRegistry = runtime.registry
    try:
        provider = registry.provider(provider_key)
    except KeyError as exc:
        raise AppError(code="PROVIDER_NOT_FOUND", message="供应商不存在", status_code=404) from exc

    zero = parse_banded_price(
        {
            "hit": {"peak": 0.0, "offpeak": 0.0},
            "miss": {"peak": 0.0, "offpeak": 0.0},
            "out": {"peak": 0.0, "offpeak": 0.0},
        }
    )
    specs: list[ModelSpec] = []
    for model_id in payload.model_ids:
        cleaned = model_id.strip()
        if not cleaned:
            continue
        key = f"{provider.key}:{cleaned}"
        if key in registry.models:
            continue
        specs.append(
            ModelSpec(
                key=key,
                provider_key=provider.key,
                model_name=cleaned,
                display_name=cleaned,
                context_window=32768,
                max_output=8192,
                supports=frozenset({Capability.STREAM}),
                price=zero,
                notes="从供应商 /v1/models 导入，上下文与价格未核实",
            )
        )
    updated = registry.with_extra_models(specs)
    runtime.registry = updated
    # 记录导入的模型，供后续热更新时保留
    extra = getattr(runtime, "extra_models", None)
    if extra is None:
        extra = {}
        runtime.extra_models = extra
    for spec in specs:
        extra[spec.key] = spec
    if hasattr(runtime, "apply_provider_settings"):
        await runtime.apply_provider_settings()
    return [spec.key for spec in specs]
