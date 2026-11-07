"""人设与伴侣的请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.persona import Persona

DimensionKey = Literal[
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


class DimensionMetaOut(BaseModel):
    key: str
    label: str
    type: str
    required: bool = False
    max_length: int | None = None
    min: int | None = None
    max: int | None = None
    min_items: int | None = None
    max_items: int | None = None
    options: list[str] | None = None
    hint: str | None = None


class PersonaSchemaOut(BaseModel):
    schema_version: int
    dimensions: list[DimensionMetaOut]
    age_min: int
    age_max: int


class PersonaDraftIn(BaseModel):
    description: str = Field(min_length=4, max_length=200)


class PersonaDraftOut(BaseModel):
    persona: Persona
    model_key: str
    cost_cny: float


class PersonaRefineIn(BaseModel):
    """按用户的一句话要求，重写人设草稿里的某个维度。

    人设由前端传入而不是按 id 查库：创建流程里伴侣还没落库，
    且草稿在用户确认前不应写进正式库（ADR-0001）。
    """

    persona: Persona
    dimension: str = Field(max_length=32)
    hint: str | None = Field(default=None, max_length=200)


class PersonaRefineOut(BaseModel):
    dimension: str
    value: Any
    model_key: str
    cost_cny: float


class CompanionCreateIn(BaseModel):
    persona: Persona
    name: str | None = Field(default=None, max_length=20)


class CompanionOut(BaseModel):
    id: int
    name: str
    current_version: int
    persona: Persona
    memory_enabled: bool = True
    avatar: str | None = None
    derived_from: int | None = None
    voice_id: str | None = None
    created_at: datetime
    updated_at: datetime


class PersonaPutIn(BaseModel):
    persona: Persona


class PersonaVersionOut(BaseModel):
    """一个人设历史版本。不含 compiled_prompt：体积大且界面用不到。"""

    version: int
    persona: Persona
    created_at: datetime


class DeriveIn(BaseModel):
    persona: Persona
    name: str | None = Field(default=None, max_length=20)


class AvatarIn(BaseModel):
    avatar: str | None = Field(default=None, max_length=500_000)


class VoiceIn(BaseModel):
    voice_id: str | None = Field(default=None, max_length=128)


class DimensionPatchIn(BaseModel):
    dimension: DimensionKey
    value: Any


class DimensionRegenerateIn(BaseModel):
    dimension: DimensionKey
    hint: str | None = Field(default=None, max_length=100)


class DimensionRegenerateOut(BaseModel):
    dimension: str
    value: Any
    model_key: str
    cost_cny: float


class TemplateOut(BaseModel):
    key: str
    category: str
    name: str
    tagline: str
    persona: Persona


class TemplateCreateIn(BaseModel):
    template_key: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=20)
