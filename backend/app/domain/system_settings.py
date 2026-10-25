"""系统设置：管理员统一配置额度与模型默认参数。

存储为一行 JSON（key="app"），服务端校验后落库并写审计；
模型参数只作用于主链路（chat_main）与人设生成（persona_generate）。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Protocol

from app.core.errors import InvalidInput

SETTINGS_KEY = "app"
ALLOWED_TASKS = ("chat_main", "persona_generate")
ALLOWED_FIELDS = ("model", "temperature", "max_tokens", "top_p", "thinking", "json_mode")

DEFAULT_SETTINGS: dict[str, object] = {
    "quota": {"enforced": False, "daily_limit": 60},
    "model_defaults": {
        "chat_main": {
            "model": "",
            "temperature": 0.8,
            "max_tokens": 512,
            "top_p": 0.95,
            "thinking": False,
            "json_mode": False,
        },
        "persona_generate": {
            "model": "",
            "temperature": 0.6,
            "max_tokens": 1200,
            "top_p": 0.95,
            "thinking": False,
            "json_mode": True,
        },
    },
}


def _merge(base: dict[str, object], patch: dict[str, object]) -> dict[str, object]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


class SystemSettingsRepository(Protocol):
    async def load(self) -> dict[str, object]: ...

    async def save(self, value: dict[str, object], actor: str) -> None: ...

    async def audit(
        self,
        actor: str,
        action: str,
        before: dict[str, object] | None,
        after: dict[str, object] | None,
    ) -> None: ...

    async def audit_tail(self, limit: int = 20) -> list[dict[str, object]]: ...


class InMemorySystemSettingsRepository:
    def __init__(self) -> None:
        self.value: dict[str, object] | None = None
        self.audits: list[dict[str, object]] = []

    async def load(self) -> dict[str, object]:
        return deepcopy(self.value) if self.value else {}

    async def save(self, value: dict[str, object], actor: str) -> None:
        self.value = deepcopy(value)
        self.actor = actor

    async def audit(
        self,
        actor: str,
        action: str,
        before: dict[str, object] | None,
        after: dict[str, object] | None,
    ) -> None:
        self.audits.append(
            {
                "actor": actor,
                "action": action,
                "before": before,
                "after": after,
                "created_at": datetime.now(UTC).isoformat(),
            }
        )

    async def audit_tail(self, limit: int = 20) -> list[dict[str, object]]:
        return list(reversed(self.audits))[:limit]


class SystemSettingsService:
    def __init__(self, repo: SystemSettingsRepository) -> None:
        self._repo = repo
        self._data: dict[str, object] = deepcopy(DEFAULT_SETTINGS)

    async def load(self) -> dict[str, object]:
        raw = await self._repo.load()
        self._data = _merge(DEFAULT_SETTINGS, raw)
        return deepcopy(self._data)

    @property
    def data(self) -> dict[str, object]:
        return deepcopy(self._data)

    def quota_config(self) -> tuple[bool, int]:
        quota = self._data.get("quota", {})
        if not isinstance(quota, dict):
            return False, 60
        enforced = bool(quota.get("enforced", False))
        limit = int(quota.get("daily_limit", 60) or 60)
        return enforced, max(limit, 1)

    def model_override(self, task: str) -> dict[str, object] | None:
        defaults = self._data.get("model_defaults", {})
        if not isinstance(defaults, dict):
            return None
        item = defaults.get(task)
        if not isinstance(item, dict):
            return None
        if not item.get("model") and all(
            item.get(field) in (None, "", False) for field in ("temperature", "max_tokens")
        ):
            return None
        return dict(item)

    async def update(
        self,
        patch: dict[str, object],
        *,
        actor: str,
        available_models: set[str] | None = None,
    ) -> dict[str, object]:
        before = deepcopy(self._data)
        merged = _merge(self._data, patch)
        validated = self._validate(merged, available_models or set())
        await self._repo.save(validated, actor)
        await self._repo.audit(actor, "settings.update", before, validated)
        self._data = validated
        return deepcopy(validated)

    def _validate(self, data: dict[str, object], available_models: set[str]) -> dict[str, object]:
        quota = data.get("quota")
        if not isinstance(quota, dict):
            raise InvalidInput("quota 配置必须是对象", code="SETTINGS_INVALID")
        if "enforced" in quota and not isinstance(quota["enforced"], bool):
            raise InvalidInput("quota.enforced 必须是布尔值", code="SETTINGS_INVALID")
        if "daily_limit" in quota:
            limit = quota["daily_limit"]
            if not isinstance(limit, int) or not 1 <= limit <= 10_000:
                raise InvalidInput("每日额度必须是 1–10000 的整数", code="SETTINGS_INVALID")

        defaults = data.get("model_defaults")
        if not isinstance(defaults, dict):
            raise InvalidInput("model_defaults 必须是对象", code="SETTINGS_INVALID")
        for task, item in defaults.items():
            if task not in ALLOWED_TASKS:
                raise InvalidInput(f"不支持配置的任务：{task}", code="SETTINGS_INVALID")
            if not isinstance(item, dict):
                raise InvalidInput(f"{task} 配置必须是对象", code="SETTINGS_INVALID")
            for field in item:
                if field not in ALLOWED_FIELDS:
                    raise InvalidInput(f"不支持的参数：{field}", code="SETTINGS_INVALID")
            model = item.get("model")
            if model:
                if not isinstance(model, str):
                    raise InvalidInput("model 必须是字符串", code="SETTINGS_INVALID")
                if available_models and model not in available_models:
                    raise InvalidInput(f"模型不存在：{model}", code="SETTINGS_INVALID")
            temperature = item.get("temperature")
            if temperature is not None:
                if not isinstance(temperature, (int, float)) or not 0 <= float(temperature) <= 2:
                    raise InvalidInput("temperature 必须在 0–2 之间", code="SETTINGS_INVALID")
            max_tokens = item.get("max_tokens")
            if max_tokens is not None:
                if not isinstance(max_tokens, int) or not 32 <= max_tokens <= 4096:
                    raise InvalidInput("max_tokens 必须在 32–4096 之间", code="SETTINGS_INVALID")
            top_p = item.get("top_p")
            if top_p is not None:
                if not isinstance(top_p, (int, float)) or not 0 <= float(top_p) <= 1:
                    raise InvalidInput("top_p 必须在 0–1 之间", code="SETTINGS_INVALID")
            for flag in ("thinking", "json_mode"):
                if flag in item and not isinstance(item[flag], bool):
                    raise InvalidInput(f"{flag} 必须是布尔值", code="SETTINGS_INVALID")
        return data
