import json
from decimal import Decimal

import pytest

from app.core.errors import AppError, InvalidInput, NotFound
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


# ---------- 草稿单维改写（创建流程里用，不落库） ----------


async def test_refine_draft_dimension_returns_value_without_saving() -> None:
    """草稿改写只返回建议值：不再查库，也不产生新版本。"""
    service = CompanionService(
        InMemoryCompanionRepository(), FakeLLM([json.dumps({"value": "句子更短更冷"})])
    )
    created = await service.create("u1", PERSONA)
    value, result = await service.refine_draft_dimension(
        "u1", created.persona, "speaking_style", "再冷一点", "req-r1"
    )
    assert value == "句子更短更冷"
    assert result.model_key == "fake:model"
    # 未保存：库里仍是旧值，版本号没变
    current = await service.get("u1", created.id)
    assert current.persona.speaking_style != "句子更短更冷"
    assert current.current_version == 1


async def test_refine_draft_works_without_existing_companion() -> None:
    """关键差异：草稿改写不要求伴侣已存在，创建流程里能直接用。"""
    service = CompanionService(
        InMemoryCompanionRepository(),
        FakeLLM([json.dumps({"value": "从小在南方小城长大，大学去了北方，习惯一个人待着"})]),
    )
    # 注意：这里完全没有 create，库里没有任何伴侣
    value, _ = await service.refine_draft_dimension(
        "u1", PERSONA, "background", "写得更具体一点", "req-r2"
    )
    assert value.startswith("从小在南方小城长大")


async def test_refine_draft_rejects_identity_fields() -> None:
    """名字/性别/年龄不接受 AI 改写：它们是身份锚点与硬约束。"""
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([json.dumps({"value": 1})]))
    for dimension in ("name", "gender", "age"):
        with pytest.raises(InvalidInput) as excinfo:
            await service.refine_draft_dimension("u1", PERSONA, dimension, None, "req-r3")
        assert excinfo.value.code == "DIMENSION_NOT_REFINABLE"


async def test_refine_draft_rejects_unknown_dimension() -> None:
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([json.dumps({"value": "x"})]))
    with pytest.raises(InvalidInput) as excinfo:
        await service.refine_draft_dimension("u1", PERSONA, "favorite_color", None, "req-r4")
    assert excinfo.value.code == "UNKNOWN_DIMENSION"


async def test_refine_draft_rejects_overlong_hint() -> None:
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([json.dumps({"value": "x"})]))
    with pytest.raises(InvalidInput) as excinfo:
        await service.refine_draft_dimension("u1", PERSONA, "background", "长" * 300, "req-r5")
    assert excinfo.value.code == "REFINE_HINT_TOO_LONG"


async def test_refine_draft_rejects_invalid_persona_after_merge() -> None:
    """新值单独看着没问题，拼回人设后不合法也要拦住。"""
    service = CompanionService(
        InMemoryCompanionRepository(), FakeLLM([json.dumps({"value": "短"})])
    )
    with pytest.raises(AppError) as excinfo:
        await service.refine_draft_dimension("u1", PERSONA, "speaking_style", None, "req-r6")
    assert excinfo.value.code == "PERSONA_GENERATION_FAILED"


async def test_refine_draft_requires_value_field() -> None:
    """模型返回了 JSON 但没有 value 字段，要给明确错误而不是静默失败。"""
    service = CompanionService(
        InMemoryCompanionRepository(), FakeLLM([json.dumps({"result": "写错了"})])
    )
    with pytest.raises(AppError) as excinfo:
        await service.refine_draft_dimension("u1", PERSONA, "background", None, "req-r7")
    assert excinfo.value.code == "PERSONA_GENERATION_FAILED"


# ---------- 人设版本历史与还原 ----------


async def test_versions_start_at_one() -> None:
    """创建即 v1：历史列表要有起点。"""
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([]))
    created = await service.create("u1", PERSONA)
    versions = await service.list_persona_versions("u1", created.id)
    assert [v.version for v in versions] == [1]


async def test_saving_persona_adds_version() -> None:
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([]))
    created = await service.create("u1", PERSONA)
    updated_persona = PERSONA.model_copy(
        update={"speaking_style": "更冷更短的句子，一次不超过十个字。"}
    )
    saved = await service.replace_persona("u1", created.id, updated_persona)
    assert saved.current_version == 2
    versions = await service.list_persona_versions("u1", created.id)
    assert [v.version for v in versions] == [2, 1]
    # 新的在前
    assert versions[0].persona.speaking_style.startswith("更冷更短")


async def test_restore_version_creates_new_version_instead_of_rewinding() -> None:
    """还原 = 复制成新版本，不是把指针拨回去。"""
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([]))
    created = await service.create("u1", PERSONA)
    original_style = created.persona.speaking_style

    # 改两次，共 3 个版本
    await service.replace_persona(
        "u1",
        created.id,
        PERSONA.model_copy(update={"speaking_style": "第二版的说话方式，比较冷静。"}),
    )
    await service.replace_persona(
        "u1",
        created.id,
        PERSONA.model_copy(update={"speaking_style": "第三版的说话方式，非常热情。"}),
    )

    restored = await service.restore_persona_version("u1", created.id, 1)
    # 还原后是 v4，内容回到 v1
    assert restored.current_version == 4
    assert restored.persona.speaking_style == original_style
    # 历史全在：4/3/2/1
    versions = await service.list_persona_versions("u1", created.id)
    assert [v.version for v in versions] == [4, 3, 2, 1]


async def test_restore_unknown_version_fails() -> None:
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([]))
    created = await service.create("u1", PERSONA)
    with pytest.raises(NotFound):
        await service.restore_persona_version("u1", created.id, 99)


async def test_versions_are_pruned_to_limit() -> None:
    """版本不会无限增长：超过上限只留最近的。"""
    from app.domain.companions import MAX_PERSONA_VERSIONS

    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([]))
    created = await service.create("u1", PERSONA)
    for index in range(MAX_PERSONA_VERSIONS + 5):
        await service.replace_persona(
            "u1",
            created.id,
            PERSONA.model_copy(update={"speaking_style": f"第 {index} 次修改后的说话方式说明。"}),
        )
    versions = await service.list_persona_versions("u1", created.id)
    assert len(versions) == MAX_PERSONA_VERSIONS


async def test_versions_are_isolated_per_user() -> None:
    service = CompanionService(InMemoryCompanionRepository(), FakeLLM([]))
    created = await service.create("u1", PERSONA)
    with pytest.raises(NotFound):
        await service.list_persona_versions("u2", created.id)
