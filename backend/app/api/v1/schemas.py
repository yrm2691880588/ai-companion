"""模型层 API 的请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProviderOut(BaseModel):
    key: str
    name: str
    kind: str
    base_url: str
    scope: str = "system"
    has_key: bool = False
    masked_key: str = ""
    allows_private: bool = False


class ModelOut(BaseModel):
    key: str
    provider_key: str
    model_name: str
    display_name: str
    context_window: int
    max_output: int
    supports: list[str]
    embedding_dim: int | None = None
    notes: str = ""


class ProviderDetailOut(ProviderOut):
    models: list[ModelOut] = Field(default_factory=list)


class RouteStepOut(BaseModel):
    model: str
    params: dict[str, object] = Field(default_factory=dict)


class RoutesOut(BaseModel):
    task: str
    chain: list[RouteStepOut]
