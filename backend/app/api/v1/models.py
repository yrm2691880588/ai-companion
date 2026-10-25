"""模型与服务 API：先提供只读的预设与路由视图，供前端接入与评审。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.schemas import ModelOut, ProviderDetailOut, RoutesOut, RouteStepOut
from app.core.errors import AppError
from app.infra.llm.registry import ModelRegistry
from app.infra.llm.types import ModelSpec, TaskName
from app.security.crypto import mask_secret

router = APIRouter(prefix="/v1", tags=["models"])


def get_registry(request: Request) -> ModelRegistry:
    registry = getattr(request.app.state, "registry", None)
    if not isinstance(registry, ModelRegistry):
        raise HTTPException(status_code=503, detail="模型注册表尚未初始化")
    return registry


RegistryDep = Annotated[ModelRegistry, Depends(get_registry)]


def _model_out(spec: ModelSpec) -> ModelOut:
    return ModelOut(
        key=spec.key,
        provider_key=spec.provider_key,
        model_name=spec.model_name,
        display_name=spec.display_name,
        context_window=spec.context_window,
        max_output=spec.max_output,
        supports=sorted(capability.value for capability in spec.supports),
        embedding_dim=spec.embedding_dim,
        notes=spec.notes,
    )


def _provider_out(registry: ModelRegistry, provider_key: str) -> ProviderDetailOut:
    provider = registry.provider(provider_key)
    return ProviderDetailOut(
        key=provider.key,
        name=provider.name,
        kind=provider.kind,
        base_url=provider.base_url,
        scope="system",
        has_key=bool(provider.api_key),
        masked_key=mask_secret(provider.api_key),
        allows_private=provider.allow_private,
        models=[_model_out(spec) for spec in registry.models_of(provider.key)],
    )


@router.get("/model-providers", response_model=list[ProviderDetailOut])
def list_providers(registry: RegistryDep) -> list[ProviderDetailOut]:
    """内置预设供应商与模型（Key 只回掩码，永不回明文）。"""
    return [_provider_out(registry, key) for key in registry.providers]


@router.get("/model-providers/{provider_key}", response_model=ProviderDetailOut)
def get_provider(provider_key: str, registry: RegistryDep) -> ProviderDetailOut:
    try:
        return _provider_out(registry, provider_key)
    except KeyError as exc:
        raise AppError(code="PROVIDER_NOT_FOUND", message="供应商不存在", status_code=404) from exc


@router.get("/model-routes", response_model=list[RoutesOut])
def list_routes(registry: RegistryDep) -> list[RoutesOut]:
    """默认任务路由（后续会支持按用户覆盖）。"""
    result: list[RoutesOut] = []
    for task in TaskName:
        try:
            steps = registry.route(task)
        except KeyError:
            continue
        result.append(
            RoutesOut(
                task=task.value,
                chain=[
                    RouteStepOut(model=step.model_key, params=dict(step.params)) for step in steps
                ],
            )
        )
    return result
