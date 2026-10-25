import pytest
from pydantic import ValidationError

from app.domain.persona import Persona


def persona(**overrides: object) -> Persona:
    data = {
        "name": "曼曼",
        "identity": "夜店驻唱歌手",
        "gender": "女",
        "age": 27,
        "personality": ["大胆", "黏人", "占有欲强"],
        "speaking_style": "说话带点沙哑的懒腔，句子短，爱用反问和拖长的尾音。",
        "background": "在城南一家小酒馆驻唱，晚上上班白天睡觉，作息和大多数人反着来。",
        "tags": ["夜场歌手", "主动"],
        "relationship": "住在你楼上的邻居",
    }
    data.update(overrides)
    return Persona.model_validate(data)


def test_adult_persona_is_allowed() -> None:
    data = persona().model_dump()
    assert data["age"] == 27


def test_age_below_18_is_rejected() -> None:
    with pytest.raises(ValidationError):
        persona(age=17)


def test_age_18_is_allowed() -> None:
    assert persona(age=18).age == 18


def test_adult_content_policy_in_chat_prompt() -> None:
    from app.domain.chat import SAFETY_NOTE

    assert "成年人" in SAFETY_NOTE
    assert "未成年" in SAFETY_NOTE
    assert "非自愿" in SAFETY_NOTE
    assert "拒绝色情" not in SAFETY_NOTE


def test_draft_prompt_requires_adult_characters() -> None:
    from app.domain.companions import _DRAFT_SYSTEM

    assert "18–99" in _DRAFT_SYSTEM
    assert "未成年" in _DRAFT_SYSTEM
    assert "非自愿" in _DRAFT_SYSTEM
