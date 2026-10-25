import pytest

from app.infra.llm.registry import ModelRegistry
from app.infra.llm.types import Capability, TaskName

REG = ModelRegistry.from_presets(env={})


def test_presets_are_loaded() -> None:
    assert len(REG.providers) == 9
    assert len(REG.models) >= 13
    assert REG.default_provider == "deepseek"


def test_deepseek_flash_matches_official_spec() -> None:
    spec = REG.model("deepseek:deepseek-flash")
    assert spec.context_window == 1_000_000
    assert spec.max_output == 384_000
    assert Capability.THINKING in spec.supports
    assert Capability.VISION in spec.supports
    assert spec.price.peak.input_miss > 0


def test_old_model_names_are_kept_as_aliases() -> None:
    spec = REG.model("deepseek:deepseek-flash")
    assert "deepseek-chat" in spec.aliases
    assert "deepseek-reasoner" in REG.model("deepseek:deepseek-v4-pro").aliases


def test_default_chat_route_is_deepseek_flash() -> None:
    assert REG.route(TaskName.CHAT_MAIN)[0].model_key == "deepseek:deepseek-flash"


def test_resolve_filters_by_capability() -> None:
    vision_chain = REG.resolve(TaskName.CHAT_MAIN, required=frozenset({Capability.VISION}))
    assert [step.model_key for step in vision_chain] == ["deepseek:deepseek-flash"]
    default_chain = REG.resolve(TaskName.CHAT_MAIN)
    assert len(default_chain) >= 2


def test_embedding_presets_use_1024_dims() -> None:
    assert REG.model("ollama:bge-m3").embedding_dim == 1024
    assert REG.model("siliconflow:BAAI/bge-m3").embedding_dim == 1024
    assert REG.model("openai:text-embedding-3-small").embedding_dim == 1536


def test_with_keys_returns_copy() -> None:
    keyed = REG.with_keys({"deepseek": "sk-test"})
    assert keyed.provider("deepseek").api_key == "sk-test"
    assert REG.provider("deepseek").api_key == ""


def test_unknown_model_raises() -> None:
    with pytest.raises(KeyError):
        REG.model("nope:model")


def test_route_references_existing_models() -> None:
    for task in TaskName:
        for step in REG.route(task):
            assert step.model_key in REG.models
