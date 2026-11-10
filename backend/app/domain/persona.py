"""人设（Persona）：7 个可编辑维度 + 身份信息，校验、编译为系统提示词。

维度与 UI 一一对应：
1 身份 identity｜2 性别 gender｜3 年龄 age｜4 性格特质 personality
5 说话风格 speaking_style｜6 背景设定 background｜7 核心标签 tags
另外 name（名字）、relationship（关系定位）、example_openers（示例开场白）是创建时的必要补充。

编译顺序按「缓存友好」排列：稳定内容在前，可变内容在后。
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.infra.llm.tokenizer import estimate_tokens

CURRENT_SCHEMA_VERSION = 1
GENDERS = ("女", "男", "其他", "不设定")
MAX_NAME = 20
MAX_FIELD = 60
MIN_AGE = 18
MAX_AGE = 99
KO = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

DIMENSION_KEYS = (
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
)


def _clean_text(value: str, *, max_length: int) -> str:
    text = KO.sub("", value).strip()
    if len(text) > max_length:
        raise ValueError(f"长度不能超过 {max_length} 字")
    return text


class Persona(BaseModel):
    """结构化人设。所有字段都可被用户逐项修改。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: int = CURRENT_SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=MAX_NAME, description="伴侣名字")
    identity: str = Field(min_length=2, max_length=MAX_FIELD, description="身份/职业角色")
    gender: Literal["女", "男", "其他", "不设定"] = "不设定"
    age: int | None = Field(default=None, ge=MIN_AGE, le=MAX_AGE)
    personality: list[str] = Field(min_length=2, max_length=8, description="性格特质")
    speaking_style: str = Field(min_length=4, max_length=200, description="说话风格")
    background: str = Field(min_length=10, max_length=800, description="背景设定")
    tags: list[str] = Field(min_length=1, max_length=8, description="核心标签")
    relationship: str = Field(default="", max_length=MAX_FIELD, description="与用户的关系定位")
    example_openers: list[str] = Field(default_factory=list, max_length=3, description="示例开场白")

    @field_validator("name", "identity", "speaking_style", "background", "relationship")
    @classmethod
    def _clean_single(cls, value: str, info: ValidationInfo) -> str:
        limits = {
            "name": MAX_NAME,
            "identity": MAX_FIELD,
            "speaking_style": 200,
            "background": 800,
            "relationship": MAX_FIELD,
        }
        return _clean_text(value, max_length=limits.get(info.field_name or "", MAX_FIELD))

    @field_validator("personality", "tags")
    @classmethod
    def _clean_list(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            item = _clean_text(value, max_length=12)
            if item and item not in cleaned:
                cleaned.append(item)
        if not cleaned:
            raise ValueError("至少需要一项")
        return cleaned

    @field_validator("example_openers")
    @classmethod
    def _clean_openers(cls, values: list[str]) -> list[str]:
        return [_clean_text(value, max_length=80) for value in values if value.strip()]

    def to_prompt(self) -> str:
        return compile_prompt(self)


def compile_prompt(persona: Persona) -> str:
    """编译成对话用的系统提示词（稳定在前，便于前缀缓存）。"""
    age_part = f"{persona.age} 岁" if persona.age else "年龄未设定"
    gender_part = "" if persona.gender == "不设定" else f"{persona.gender}性，"
    lines = [
        "# 你是谁",
        f"你是{persona.name}，{gender_part}{age_part}，{persona.identity}。",
    ]
    if persona.relationship:
        lines.append(f"你和用户的关系：{persona.relationship}。")
    lines.extend(
        [
            "",
            "# 性格",
            "、".join(persona.personality) + "。",
            "",
            "# 说话方式",
            persona.speaking_style,
            "",
            "# 背景",
            persona.background,
            "",
            "# 人设标签",
            "、".join(persona.tags) + "。",
            "",
            "# 对话要求",
            "- 始终以这个角色的身份、语气和认知水平说话，不要跳出角色，不要说自己是 AI 或模型。",
            "- 保持简洁口语化，一次回复 1–3 句；除非用户要求展开，不要长篇大论。",
            "- 不要用列表、编号、标题来回复日常对话。",
            "- 不确定的事就说不知道，不要编造共同经历；只使用对话里出现过的信息。",
        ]
    )
    if persona.example_openers:
        lines.extend(["", "# 你说话的感觉（仅供参考，不要照抄）"])
        lines.extend(f"- {opener}" for opener in persona.example_openers)
    return "\n".join(lines)


def prompt_tokens(persona: Persona) -> int:
    return estimate_tokens(compile_prompt(persona))


DIMENSION_META: list[dict[str, Any]] = [
    {
        "key": "name",
        "refinable": False,
        "label": "名字",
        "type": "text",
        "required": True,
        "max_length": MAX_NAME,
        "hint": "2–8 个字最好记",
    },
    {
        "key": "identity",
        "refinable": True,
        "label": "身份",
        "type": "text",
        "required": True,
        "max_length": MAX_FIELD,
        "hint": "例如：心理学研究生、产品经理、健身教练",
    },
    {
        "key": "gender",
        "refinable": False,
        "label": "性别",
        "type": "select",
        "required": True,
        "options": list(GENDERS),
    },
    {
        "key": "age",
        "refinable": False,
        "label": "年龄",
        "type": "number",
        "required": False,
        "min": MIN_AGE,
        "max": MAX_AGE,
    },
    {
        "key": "personality",
        "refinable": True,
        "label": "性格特质",
        "type": "list",
        "required": True,
        "min_items": 2,
        "max_items": 8,
        "hint": "写 2–6 个词，最好带一点矛盾感",
    },
    {
        "key": "speaking_style",
        "refinable": True,
        "label": "说话风格",
        "type": "textarea",
        "required": True,
        "max_length": 200,
        "hint": "句长、用词、有没有口头禅、会不会用表情",
    },
    {
        "key": "background",
        "refinable": True,
        "label": "背景设定",
        "type": "textarea",
        "required": True,
        "max_length": 800,
        "hint": "经历、专业、当前处境，3–5 句",
    },
    {
        "key": "tags",
        "refinable": True,
        "label": "核心标签",
        "type": "list",
        "required": True,
        "min_items": 1,
        "max_items": 8,
        "hint": "例如：温柔、毒舌学姐、职场导师",
    },
    {
        "key": "relationship",
        "refinable": True,
        "label": "关系定位",
        "type": "text",
        "required": False,
        "max_length": MAX_FIELD,
        "hint": "例如：住在隔壁的学姐、带你的前辈",
    },
    {
        "key": "example_openers",
        "refinable": True,
        "label": "示例开场白",
        "type": "list",
        "required": False,
        "max_items": 3,
        "hint": "2–3 句这个人会说的话",
    },
]

# 哪些维度允许交给 AI 改写。
#
# 由 DIMENSION_META 派生，不再手写第二份清单：
# 名字是用户的身份锚点，性别年龄是硬约束，交给 AI 改没有意义且容易跑偏。
# 以后新增人设字段时，只要在 DIMENSION_META 里标好 refinable，
# 这里和调用方都会自动跟着变。
REFINABLE_DIMENSIONS: tuple[str, ...] = tuple(
    item["key"] for item in DIMENSION_META if item.get("refinable")
)
