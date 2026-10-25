from datetime import datetime
from zoneinfo import ZoneInfo

from app.infra.llm.registry import ModelRegistry
from app.infra.llm.router import ModelRouter
from app.infra.llm.types import ChatChunk, Message, Role, TaskName

SHANGHAI = ZoneInfo("Asia/Shanghai")
REG = ModelRegistry.from_presets(env={})


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def astream(self, provider, spec, messages, params, *, telemetry=None):  # type: ignore[no-untyped-def]
        self.calls.append(spec)
        yield ChatChunk(delta="ok", model_key=spec.key)


def router(overrides: dict[str, object] | None) -> ModelRouter:
    return ModelRouter(
        REG,
        FakeGateway(),  # type: ignore[arg-type]
        clock=lambda: datetime(2026, 10, 26, 10, 0, tzinfo=SHANGHAI),
        overrides=lambda task: overrides if task == "chat_main" else None,
    )


def test_override_moves_model_to_front() -> None:
    plan = router({"model": "deepseek:deepseek-v4-pro"}).plan(TaskName.CHAT_MAIN)
    assert plan[0].spec.key == "deepseek:deepseek-v4-pro"
    assert "deepseek:deepseek-flash" in [item.spec.key for item in plan]


def test_override_applies_params_to_primary() -> None:
    plan = router({"temperature": 0.1, "max_tokens": 64}).plan(TaskName.CHAT_MAIN)
    params = plan[0].step.params
    assert params["temperature"] == 0.1
    assert params["max_tokens"] == 64


def test_unknown_override_model_is_ignored() -> None:
    plan = router({"model": "nope:nope"}).plan(TaskName.CHAT_MAIN)
    assert plan[0].spec.key == "deepseek:deepseek-flash"


def test_override_only_applies_to_configured_task() -> None:
    plan = router({"temperature": 0.1}).plan(TaskName.MEMORY_EXTRACT)
    assert plan[0].step.params["temperature"] == 0


async def test_override_model_is_used_for_stream() -> None:
    gw = FakeGateway()
    router_instance = ModelRouter(
        REG,
        gw,  # type: ignore[arg-type]
        clock=lambda: datetime(2026, 10, 26, 10, 0, tzinfo=SHANGHAI),
        overrides=lambda task: {"model": "deepseek:deepseek-v4-pro"},
    )
    chunks = [
        chunk
        async for chunk in router_instance.stream(
            TaskName.CHAT_MAIN, [Message(role=Role.USER, content="hi")]
        )
    ]
    assert chunks
    assert chunks[0].model_key == "deepseek:deepseek-v4-pro"
