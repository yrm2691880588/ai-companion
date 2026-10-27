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
