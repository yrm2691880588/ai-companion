"""模型注册表：从 presets.yaml 载入供应商、模型档案与默认路由。

运行时把 API Key 注入（系统预设读环境变量，用户自带 Key 从数据库解密后注入），
业务代码只认「模型 key」，不认具体供应商。
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from app.infra.llm.pricing import BandedPrice, parse_banded_price
from app.infra.llm.types import Capability, ModelSpec, ProviderConfig, TaskName

PRESETS_PATH = Path(__file__).with_name("presets.yaml")


@dataclass(frozen=True, slots=True)
class RouteStep:
    model_key: str
    params: dict[str, object]


def _zero_price() -> BandedPrice:
    zero = {"peak": 0.0, "offpeak": 0.0}
    return parse_banded_price({"hit": zero, "miss": zero, "out": zero})


class ModelRegistry:
    def __init__(
        self,
        providers: Mapping[str, ProviderConfig],
        models: Mapping[str, ModelSpec],
        routes: Mapping[TaskName, tuple[RouteStep, ...]],
        *,
        default_provider: str | None = None,
    ) -> None:
        self._providers = dict(providers)
        self._models = dict(models)
        self._routes = dict(routes)
        self.default_provider = default_provider

    # ---------- 读取 ----------
    @property
    def providers(self) -> Mapping[str, ProviderConfig]:
        return self._providers

    @property
    def models(self) -> Mapping[str, ModelSpec]:
        return self._models

    def provider(self, key: str) -> ProviderConfig:
        try:
            return self._providers[key]
        except KeyError as exc:
            raise KeyError(f"未注册的供应商：{key}") from exc

    def model(self, key: str) -> ModelSpec:
        try:
            return self._models[key]
        except KeyError as exc:
            raise KeyError(f"未注册的模型：{key}") from exc

    def models_of(self, provider_key: str) -> list[ModelSpec]:
        return [m for m in self._models.values() if m.provider_key == provider_key]

    def route(self, task: TaskName | str) -> tuple[RouteStep, ...]:
        try:
            return self._routes[TaskName(task)]
        except KeyError as exc:
            raise KeyError(f"未配置的任务路由：{task}") from exc

    # ---------- 派生 ----------
    def with_keys(self, keys: Mapping[str, str]) -> ModelRegistry:
        """返回注入了 API Key 的副本（不修改原注册表）。"""
        providers = {
            key: replace(provider, api_key=keys.get(key, provider.api_key))
            for key, provider in self._providers.items()
        }
        return ModelRegistry(
            providers, self._models, self._routes, default_provider=self.default_provider
        )

    def with_routes(self, routes: Mapping[TaskName, Sequence[RouteStep]]) -> ModelRegistry:
        return ModelRegistry(
            self._providers,
            self._models,
            {TaskName(task): tuple(steps) for task, steps in routes.items()},
            default_provider=self.default_provider,
        )

    def with_extra_models(self, specs: Sequence[ModelSpec]) -> ModelRegistry:
        """把用户从供应商 /v1/models 发现的模型加入注册表（已存在则跳过）。"""
        models = dict(self._models)
        for spec in specs:
            models.setdefault(spec.key, spec)
        return ModelRegistry(
            self._providers, models, self._routes, default_provider=self.default_provider
        )

    def resolve(
        self,
        task: TaskName | str,
        *,
        required: frozenset[Capability] = frozenset(),
    ) -> list[RouteStep]:
        """按任务取路由链，并过滤掉不支持所需能力的模型。"""
        steps = self.route(task)
        filtered = [step for step in steps if self.model(step.model_key).supports_all(required)]
        return filtered

    # ---------- 载入 ----------
    @classmethod
    def from_presets(
        cls,
        path: Path | str = PRESETS_PATH,
        *,
        env: Mapping[str, str] | None = None,
        keys: Mapping[str, str] | None = None,
        only_providers: Sequence[str] | None = None,
    ) -> ModelRegistry:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("presets.yaml 顶层必须是对象")
        environ = env if env is not None else os.environ
        providers: dict[str, ProviderConfig] = {}
        models: dict[str, ModelSpec] = {}
        default_provider: str | None = None

        for item in raw.get("providers", []):
            key = str(item["key"])
            if only_providers is not None and key not in only_providers:
                continue
            api_key_env = item.get("api_key_env")
            api_key = str(environ.get(api_key_env, "")) if api_key_env else ""
            if keys and keys.get(key):
                api_key = str(keys[key])
            providers[key] = ProviderConfig(
                key=key,
                name=str(item["name"]),
                kind=str(item.get("kind", "openai")),
                base_url=str(item["base_url"]),
                api_key=api_key,
                allow_private=bool(item.get("allow_private", False)),
                thinking_style=str(item.get("thinking_style", "none")),
            )
            if item.get("default"):
                default_provider = key
            for model_raw in item.get("models", []):
                spec = _parse_model(key, model_raw)
                models[spec.key] = spec

        routes: dict[TaskName, tuple[RouteStep, ...]] = {}
        for task, route_raw in (raw.get("routes") or {}).items():
            steps = []
            for step_raw in route_raw.get("chain", []):
                model_key = str(step_raw["model"])
                if model_key not in models:
                    raise ValueError(f"路由 {task} 引用了不存在的模型：{model_key}")
                params = {k: v for k, v in step_raw.items() if k != "model"}
                steps.append(RouteStep(model_key=model_key, params=params))
            routes[TaskName(task)] = tuple(steps)

        return cls(providers, models, routes, default_provider=default_provider)


def _parse_model(provider_key: str, raw: dict[str, Any]) -> ModelSpec:
    pricing_raw = raw.get("pricing")
    price = parse_banded_price(pricing_raw) if isinstance(pricing_raw, dict) else _zero_price()
    supports = frozenset(Capability(value) for value in raw.get("supports", []))
    return ModelSpec(
        key=f"{provider_key}:{raw['model_name']}",
        provider_key=provider_key,
        model_name=str(raw["model_name"]),
        display_name=str(raw.get("display_name", raw["model_name"])),
        context_window=int(raw.get("context_window", 32768)),
        max_output=int(raw.get("max_output", 4096)),
        supports=supports,
        price=price,
        embedding_dim=int(raw["embedding_dim"]) if raw.get("embedding_dim") else None,
        aliases=tuple(str(alias) for alias in raw.get("aliases", [])),
        notes=str(raw.get("notes", "")),
    )
