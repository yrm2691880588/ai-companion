"""从供应商的 /v1/models 拉取可用模型清单。"""

from __future__ import annotations

import httpx

from app.core.errors import AppError
from app.infra.llm.types import ProviderConfig


class ModelDiscovery:
    def __init__(self, *, timeout_seconds: float = 15.0) -> None:
        self._timeout = timeout_seconds

    async def list_models(self, provider: ProviderConfig) -> list[dict[str, object]]:
        """返回 [{id, owned_by}]；失败抛 AppError。"""
        if not provider.api_key:
            raise AppError(
                code="PROVIDER_NO_KEY",
                message="请先配置 API Key，再搜索可用模型",
                status_code=400,
            )
        url = provider.base_url.rstrip("/") + "/v1/models"
        headers = {"Authorization": f"Bearer {provider.api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise AppError(
                code="PROVIDER_UNREACHABLE",
                message=f"无法连接供应商：{exc}",
                status_code=502,
            ) from exc
        if response.status_code in (401, 403):
            raise AppError(
                code="PROVIDER_AUTH_ERROR",
                message="API Key 无效或没有权限",
                status_code=400,
            )
        if response.status_code >= 400:
            raise AppError(
                code="PROVIDER_ERROR",
                message=f"供应商返回 {response.status_code}",
                status_code=502,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AppError(
                code="PROVIDER_BAD_RESPONSE", message="供应商返回的不是 JSON", status_code=502
            ) from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise AppError(
                code="PROVIDER_BAD_RESPONSE", message="供应商没有返回模型列表", status_code=502
            )
        result: list[dict[str, object]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id") or item.get("model")
            if not isinstance(model_id, str) or not model_id:
                continue
            result.append({"id": model_id, "owned_by": str(item.get("owned_by") or "")})
        result.sort(key=lambda item: str(item["id"]))
        return result
