from app.infra.llm.adapters.openai import build_payload
from app.infra.llm.registry import ModelRegistry
from app.infra.llm.types import ChatParams, Message, Role

REG = ModelRegistry.from_presets(env={})


def payload(params: ChatParams) -> dict[str, object]:
    spec = REG.model("deepseek:deepseek-flash")
    provider = REG.provider("deepseek")
    return build_payload(
        provider,
        spec,
        [Message(role=Role.USER, content="hi")],
        params,
    )


def test_payload_contains_sampling_params() -> None:
    data = payload(
        ChatParams(temperature=0.3, max_tokens=256, top_p=0.7, thinking=True, json_mode=True)
    )
    assert data["temperature"] == 0.3
    assert data["max_tokens"] == 256
    assert data["top_p"] == 0.7
    assert data["response_format"] == {"type": "json_object"}
    assert data["thinking"] == {"type": "enabled"}


def test_thinking_is_explicitly_disabled_for_deepseek() -> None:
    data = payload(ChatParams(thinking=False))
    assert data["thinking"] == {"type": "disabled"}


def test_top_p_is_omitted_when_not_set() -> None:
    assert "top_p" not in payload(ChatParams())
