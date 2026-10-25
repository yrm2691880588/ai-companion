import pytest

from app.core.errors import InvalidInput
from app.domain.system_settings import (
    DEFAULT_SETTINGS,
    InMemorySystemSettingsRepository,
    SystemSettingsService,
)


def build() -> tuple[SystemSettingsService, InMemorySystemSettingsRepository]:
    repo = InMemorySystemSettingsRepository()
    service = SystemSettingsService(repo)
    return service, repo


async def test_defaults_are_loaded() -> None:
    service, _ = build()
    await service.load()
    assert service.quota_config() == (False, 60)
    override = service.model_override("chat_main")
    assert override is not None
    assert override["temperature"] == 0.8


async def test_update_quota_and_model_defaults() -> None:
    service, repo = build()
    await service.load()
    data = await service.update(
        {
            "quota": {"enforced": True, "daily_limit": 2},
            "model_defaults": {
                "chat_main": {"temperature": 0.3, "max_tokens": 128, "thinking": False}
            },
        },
        actor="admin-1",
        available_models={"deepseek:deepseek-flash"},
    )
    assert data["quota"] == {"enforced": True, "daily_limit": 2}
    assert service.quota_config() == (True, 2)
    override = service.model_override("chat_main")
    assert override is not None and override["temperature"] == 0.3
    assert len(repo.audits) == 1
    assert repo.audits[0]["actor"] == "admin-1"


async def test_invalid_temperature_is_rejected() -> None:
    service, _ = build()
    await service.load()
    with pytest.raises(InvalidInput):
        await service.update({"model_defaults": {"chat_main": {"temperature": 5}}}, actor="a")


async def test_unknown_model_is_rejected() -> None:
    service, _ = build()
    await service.load()
    with pytest.raises(InvalidInput):
        await service.update(
            {"model_defaults": {"chat_main": {"model": "nope:nope"}}},
            actor="a",
            available_models={"deepseek:deepseek-flash"},
        )


async def test_unknown_task_is_rejected() -> None:
    service, _ = build()
    await service.load()
    with pytest.raises(InvalidInput):
        await service.update({"model_defaults": {"summary": {"temperature": 0.3}}}, actor="a")


def test_default_settings_shape() -> None:
    assert DEFAULT_SETTINGS["quota"] == {"enforced": False, "daily_limit": 60}
    assert set(DEFAULT_SETTINGS["model_defaults"]) == {"chat_main", "persona_generate"}
