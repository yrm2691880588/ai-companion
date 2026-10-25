import pytest
from pydantic import ValidationError

from app.domain.persona import (
    DIMENSION_META,
    Persona,
    compile_prompt,
    prompt_tokens,
)


def persona(**overrides: object) -> Persona:
    data: dict[str, object] = {
        "name": "林夏",
        "identity": "心理学研究生",
        "gender": "女",
        "age": 24,
        "personality": ["温柔", "偶尔毒舌"],
        "speaking_style": "句子短，口语化，先共情再给建议。",
        "background": "在读心理学研究生，晚上在便利店做兼职，见过很多深夜的人。",
        "tags": ["温柔", "毒舌学姐"],
        "relationship": "住在隔壁的学姐",
        "example_openers": ["今天怎么这么晚才回来？"],
    }
    data.update(overrides)
    return Persona.model_validate(data)


def test_persona_accepts_valid_payload() -> None:
    item = persona()
    assert item.name == "林夏"
    assert item.age == 24


def test_persona_dedupes_list_fields() -> None:
    item = persona(personality=["温柔", "温柔", "毒舌"])
    assert item.personality == ["温柔", "毒舌"]


def test_persona_strips_control_characters() -> None:
    item = persona(name="林\x00夏")
    assert item.name == "林夏"


def test_persona_rejects_too_few_personality_traits() -> None:
    with pytest.raises(ValidationError):
        persona(personality=["温柔"])


def test_persona_rejects_minor_age() -> None:
    with pytest.raises(ValidationError):
        persona(age=15)


def test_persona_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        Persona.model_validate({**persona().model_dump(), "surprise": 1})


def test_compile_prompt_has_stable_sections_in_order() -> None:
    text = compile_prompt(persona())
    sections = ["# 你是谁", "# 性格", "# 说话方式", "# 背景", "# 人设标签", "# 对话要求"]
    positions = [text.index(section) for section in sections]
    assert positions == sorted(positions)
    assert "林夏" in text
    assert "心理学研究生" in text
    assert "不要跳出角色" in text


def test_compile_prompt_includes_relationship_and_openers() -> None:
    text = compile_prompt(persona())
    assert "住在隔壁的学姐" in text
    assert "今天怎么这么晚才回来？" in text


def test_prompt_tokens_is_positive_and_bounded() -> None:
    tokens = prompt_tokens(persona())
    assert 50 < tokens < 800


def test_dimension_meta_covers_all_editable_fields() -> None:
    keys = [item["key"] for item in DIMENSION_META]
    assert keys == [
        "name",
        "identity",
        "gender",
        "age",
        "personality",
        "speaking_style",
        "background",
        "tags",
        "relationship",
        "example_openers",
    ]
