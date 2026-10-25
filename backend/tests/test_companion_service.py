import json
from decimal import Decimal

import pytest

from app.core.errors import AppError, InvalidInput
from app.domain.companions import (
    MAX_COMPANIONS,
    CompanionService,
    InMemoryCompanionRepository,
    LLMResult,
)
from app.domain.persona import Persona
from app.domain.usage import CallContext
from app.infra.llm.types import Message, TaskName, Usage

PERSONA_JSON = json.dumps(
    {
        "name": "林夏",
        "identity": "心理学研究生",
        "gender": "女",
        "age": 24,
        "personality": ["温柔", "偶尔毒舌", "共情力强"],
        "speaking_style": "句子短，口语化，先共情再给建议，偶尔用反问。",
        "background": "在读心理学研究生，晚上在便利店做兼职，见过很多深夜的人。",
        "tags": ["温柔", "毒舌学姐", "夜猫子"],
        "relationship": "住在隔壁的学姐",
        "example_openers": ["今天怎么这么晚才回来？", "先别急着想办法，说说你现在什么感觉。"],
    },
    ensure_ascii=False,
)

PERSONA = Persona.model_validate(json.loads(PERSONA_JSON))


class FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def complete(
        self, task: TaskName, messages: list[Message], *, context: CallContext
    ) -> LLMResult:
        self.calls += 1
        text = self.responses.pop(0)
        return LLMResult(
            text=text,
            model_key="fake:model",
            usage=Usage(prompt_tokens=100, completion_tokens=80),
            cost_cny=Decimal("0.0002"),
        )


async def test_generate_persona_parses_json() -> None:
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([PERSONA_JSON]))
    persona, result = await service.generate_persona("u1", "想要一个温柔的学姐", "req-1")
    assert persona.name == "林夏"
    assert result.model_key == "fake:model"


async def test_generate_persona_repairs_invalid_output_once() -> None:
    llm = FakeLLM(["这不是 JSON", PERSONA_JSON])
    service = CompanionService(InMemoryCompanionRepository(), llm)
    persona, _ = await service.generate_persona("u1", "想要一个温柔的学姐", "req-1")
    assert persona.name == "林夏"
    assert llm.calls == 2


async def test_generate_persona_fails_after_two_bad_outputs() -> None:
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM(["坏", "还是坏"]))
    with pytest.raises(AppError) as excinfo:
        await service.generate_persona("u1", "想要一个温柔的学姐", "req-1")
    assert excinfo.value.code == "PERSONA_GENERATION_FAILED"


async def test_generate_rejects_short_description() -> None:
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([PERSONA_JSON]))
    with pytest.raises(InvalidInput):
        await service.generate_persona("u1", "嗯", "req-1")


async def test_create_and_patch_creates_new_version() -> None:
    repo = InMemoryCompanionRepository()
    service = CompanionService(repo, FakeLLM([]))
    created = await service.create("u1", PERSONA)
    assert created.current_version == 1
    updated = await service.patch_dimension(
        "u1", created.id, "speaking_style", "句子更短，偶尔用表情。"
    )
    assert updated.current_version == 2
    assert updated.persona.speaking_style == "句子更短，偶尔用表情。"
    assert updated.persona.name == PERSONA.name


async def test_patch_rejects_unknown_dimension() -> None:
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([]))
    created = await service.create("u1", PERSONA)
    with pytest.raises(InvalidInput):
        await service.patch_dimension("u1", created.id, "身高", "180")


async def test_companion_limit() -> None:
    repo = InMemoryCompanionRepository()
    service = CompanionService(repo, FakeLLM([]))
    for _ in range(MAX_COMPANIONS):
        await service.create("u1", PERSONA)
    with pytest.raises(AppError) as excinfo:
        await service.create("u1", PERSONA)
    assert excinfo.value.code == "COMPANION_LIMIT"


async def test_get_other_users_companion_is_not_found() -> None:
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([]))
    created = await service.create("u1", PERSONA)
    with pytest.raises(AppError) as excinfo:
        await service.get("u2", created.id)
    assert excinfo.value.status_code == 404


async def test_regenerate_dimension_returns_value_without_saving() -> None:
    service = CompanionService(
        InMemoryCompanionRepository(), FakeLLM([json.dumps({"value": "句子更短更冷"})])
    )
    created = await service.create("u1", PERSONA)
    value, result = await service.regenerate_dimension(
        "u1", created.id, "speaking_style", "再冷一点", "req-2"
    )
    assert value == "句子更短更冷"
    assert result.model_key == "fake:model"
    # 未保存：当前人设仍是旧值
    current = await service.get("u1", created.id)
    assert current.persona.speaking_style != "句子更短更冷"
    assert current.current_version == 1


async def test_regenerate_rejects_invalid_value() -> None:
    service = CompanionService(
        InMemoryCompanionRepository(), FakeLLM([json.dumps({"value": "短"})])
    )
    created = await service.create("u1", PERSONA)
    with pytest.raises(AppError) as excinfo:
        await service.regenerate_dimension("u1", created.id, "speaking_style", None, "req-3")
    assert excinfo.value.code == "PERSONA_GENERATION_FAILED"
