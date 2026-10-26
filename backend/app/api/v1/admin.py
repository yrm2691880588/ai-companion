"""管理员接口：统一额度与模型参数、审计查询。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.deps import require_admin
from app.core.errors import AppError
from app.domain.system_settings import SystemSettingsService

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def get_settings_service(request: Request) -> SystemSettingsService:
    service = getattr(request.app.state, "system_settings", None)
    if not isinstance(service, SystemSettingsService):
        raise AppError(code="SETTINGS_UNAVAILABLE", message="系统设置不可用", status_code=503)
    return service


SettingsDep = Annotated[SystemSettingsService, Depends(get_settings_service)]
AdminDep = Annotated[str, Depends(require_admin)]


class SettingsPatch(BaseModel):
    quota: dict[str, Any] | None = None
    model_defaults: dict[str, Any] | None = None


class SettingsOut(BaseModel):
    settings: dict[str, Any]
    models: list[dict[str, Any]]


def _models(request: Request) -> list[dict[str, Any]]:
    """只返回当前真正可用的模型：供应商已配置 Key（或本地供应商已启用）。"""
    registry = request.app.state.registry
    settings_service = getattr(request.app.state, "provider_settings_service", None)
    stored: dict[str, Any] = {}
    if settings_service is not None:
        stored = getattr(settings_service, "_cached", {}) or {}
    result: list[dict[str, Any]] = []
    for spec in registry.models.values():
        provider = registry.provider(spec.provider_key)
        setting = stored.get(spec.provider_key)
        if setting is not None and not setting.enabled:
            continue
        # 云端看 Key；本地供应商必须由用户显式配置并启用
        if provider.api_key:
            available = True
        elif provider.allow_private:
            available = setting is not None
        else:
            available = False
        if not available:
            continue
        result.append(
            {
                "key": spec.key,
                "display_name": spec.display_name,
                "provider": spec.provider_key,
                "context_window": spec.context_window,
                "max_output": spec.max_output,
            }
        )
    return result


@router.get("/settings", response_model=SettingsOut)
async def get_settings(
    request: Request,
    _admin: AdminDep,
    service: SettingsDep,
) -> SettingsOut:
    return SettingsOut(settings=service.data, models=_models(request))


@router.put("/settings", response_model=SettingsOut)
async def update_settings(
    request: Request,
    payload: SettingsPatch,
    admin: AdminDep,
    service: SettingsDep,
) -> SettingsOut:
    patch = payload.model_dump(exclude_none=True)
    registry = request.app.state.registry
    data = await service.update(patch, actor=admin, available_models=set(registry.models.keys()))
    quota = request.app.state.quota_service
    enforced, limit = service.quota_config()
    quota.configure(enforced=enforced, daily_limit=limit)
    return SettingsOut(settings=data, models=_models(request))


@router.get("/audit")
async def audit_tail(
    _admin: AdminDep,
    request: Request,
    limit: int = 20,
) -> list[dict[str, Any]]:
    service = get_settings_service(request)
    repo = service._repo  # noqa: SLF001 - 审计查询直接走仓储，避免再包一层
    return await repo.audit_tail(max(1, min(limit, 100)))

