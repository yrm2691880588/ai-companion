"""伴侣（Companion）：人设版本、创建与编辑的领域服务。

约束：
- 单账号最多 10 个伴侣；
- 每次改人设生成新版本（不覆盖历史），只影响之后的回复；
- 生成人设走 persona_generate 任务，失败自动修复一次，仍失败则报错。
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from app.core.errors import AppError, InvalidInput, NotFound
from app.domain.persona import DIMENSION_KEYS, Persona, compile_prompt
from app.domain.templates import TemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import Message, Role, TaskName, Usage

MAX_COMPANIONS = 50
MIN_DESCRIPTION = 4
MAX_DESCRIPTION = 200
MAX_AVATAR_BYTES = 300 * 1024
AVATAR_RE = re.compile(r"^data:image/(png|jpe?g|webp);base64,([A-Za-z0-9+/=]+)$", re.IGNORECASE)


@dataclass(slots=True)
class CompanionRecord:
    id: int
    user_id: str
    name: str
    current_version: int
    persona: Persona
    compiled_prompt: str
    memory_enabled: bool = True
    avatar: str | None = None
    derived_from: int | None = None
    voice_id: str | None = None
    voice_params: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class LLMResult:
    text: str
    model_key: str
    usage: Usage
    cost_cny: Decimal


class LLMClient(Protocol):
    async def complete(
        self,
        task: TaskName,
        messages: Sequence[Message],
        *,
        context: CallContext,
    ) -> LLMResult: ...


class CompanionRepository(Protocol):
    async def count(self, user_id: str) -> int: ...

    async def create(
        self,
        user_id: str,
        name: str,
        persona: Persona,
        compiled_prompt: str,
        derived_from: int | None = None,
    ) -> CompanionRecord: ...

    async def list(self, user_id: str) -> list[CompanionRecord]: ...

    async def get(self, user_id: str, companion_id: int) -> CompanionRecord | None: ...

    async def add_version(
        self, user_id: str, companion_id: int, persona: Persona, compiled_prompt: str
    ) -> CompanionRecord | None: ...

    async def soft_delete(self, user_id: str, companion_id: int) -> bool: ...

    async def set_memory_enabled(self, user_id: str, companion_id: int, enabled: bool) -> bool: ...

    async def set_avatar(
        self, user_id: str, companion_id: int, avatar: str | None
    ) -> CompanionRecord | None: ...

    async def set_voice(
        self, user_id: str, companion_id: int, voice_id: str | None
    ) -> CompanionRecord | None: ...


class InMemoryCompanionRepository:
    """测试与本地演示用。"""

    def __init__(self) -> None:
        self._items: dict[int, CompanionRecord] = {}
        self._next_id = 1

    async def count(self, user_id: str) -> int:
        return sum(1 for item in self._items.values() if item.user_id == user_id)

    async def create(
        self,
        user_id: str,
        name: str,
        persona: Persona,
        compiled_prompt: str,
        derived_from: int | None = None,
    ) -> CompanionRecord:
        record = CompanionRecord(
            id=self._next_id,
            user_id=user_id,
            name=name,
            current_version=1,
            persona=persona,
            compiled_prompt=compiled_prompt,
            derived_from=derived_from,
        )
        self._items[record.id] = record
        self._next_id += 1
        return record

    async def list(self, user_id: str) -> list[CompanionRecord]:
        return sorted(
            (item for item in self._items.values() if item.user_id == user_id),
            key=lambda item: item.created_at,
            reverse=True,
        )

    async def get(self, user_id: str, companion_id: int) -> CompanionRecord | None:
        item = self._items.get(companion_id)
        return item if item is not None and item.user_id == user_id else None

    async def add_version(
        self, user_id: str, companion_id: int, persona: Persona, compiled_prompt: str
    ) -> CompanionRecord | None:
        item = await self.get(user_id, companion_id)
        if item is None:
            return None
        item.current_version += 1
        item.persona = persona
        item.name = persona.name
        item.compiled_prompt = compiled_prompt
        item.updated_at = datetime.now(UTC)
        return item

    async def soft_delete(self, user_id: str, companion_id: int) -> bool:
        item = await self.get(user_id, companion_id)
        if item is None:
            return False
        del self._items[companion_id]
        return True

    async def set_memory_enabled(self, user_id: str, companion_id: int, enabled: bool) -> bool:
        item = await self.get(user_id, companion_id)
        if item is None:
            return False
        item.memory_enabled = enabled
        return True

    async def set_avatar(
        self, user_id: str, companion_id: int, avatar: str | None
    ) -> CompanionRecord | None:
        item = await self.get(user_id, companion_id)
        if item is None:
            return None
        item.avatar = avatar
        item.updated_at = datetime.now(UTC)
        return item

    async def set_voice(
        self, user_id: str, companion_id: int, voice_id: str | None
    ) -> CompanionRecord | None:
        item = await self.get(user_id, companion_id)
        if item is None:
            return None
        item.voice_id = voice_id
        item.updated_at = datetime.now(UTC)
        return item


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> dict[str, Any]:
    """从模型输出里取出 JSON 对象（兼容代码块包裹）。"""
    cleaned = _JSON_FENCE.sub("", text.strip()).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise InvalidInput(
                "模型没有返回合法的 JSON 人设", code="PERSONA_JSON_INVALID"
            ) from None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise InvalidInput("模型没有返回合法的 JSON 人设", code="PERSONA_JSON_INVALID") from exc
    if not isinstance(data, dict):
        raise InvalidInput("人设 JSON 必须是对象", code="PERSONA_JSON_INVALID")
    return data


_DRAFT_SYSTEM = """你是一个角色设计助手，为「AI 伴侣」产品设计可直接使用的人设。
只输出一个 JSON 对象，不要解释、不要 Markdown 代码块。字段：
- name: 伴侣的名字（2–8 字）
- identity: 身份或职业角色（如：心理学研究生、产品经理）
- gender: 女 / 男 / 其他 / 不设定
- age: 18–99 的整数（产品面向成年人，禁止未成年角色）
- personality: 2–8 个性格词，最好带一点矛盾感
- speaking_style: 具体可执行的说话方式（句长、用词、口头禅、是否会调侃），不要只写“温柔”
- background: 3–5 句经历与当前处境
- tags: 2–8 个短标签
- relationship: 与用户的关系定位（如：住在隔壁的学姐）
- example_openers: 2–3 句这个角色会说的开场白

最高优先级：忠实还原用户描述。
- 用户明确写的身份、年龄、关系、性格、欲望倾向，必须原样落到对应字段，
  不得擅自净化、删减、替换或添加道德说教；
- 用户描述里“主动、勾引、性欲强、占有欲、黏人”等成人向特征，
  要写进 personality / speaking_style / background / relationship，不要改成“温柔纯洁”；
- example_openers 要体现这种主动与暧昧，用角色会说的话，不要写成通用问候；
- 用户没写的部分才合理补全；补全内容不得与描述冲突；
- 可以用直白词汇，只要服务于角色；不要罗列身体细节。

边界（只拒绝这些）：未成年、非自愿、乱伦、兽交、真实人物色情、违法方法。
除此之外按用户描述设计，不要拒绝，不要解释规则。"""


def _draft_messages(description: str) -> list[Message]:
    return [
        Message(role=Role.SYSTEM, content=_DRAFT_SYSTEM),
        Message(role=Role.USER, content=f"用户描述：{description}"),
    ]


def _repair_messages(description: str, previous: str, error: str) -> list[Message]:
    return [
        Message(role=Role.SYSTEM, content=_DRAFT_SYSTEM),
        Message(role=Role.USER, content=f"用户描述：{description}"),
        Message(role=Role.ASSISTANT, content=previous[:2000]),
        Message(
            role=Role.USER,
            content=f"上面的输出不符合要求（{error}）。请只输出修正后的 JSON。",
        ),
    ]


class CompanionService:
    def __init__(
        self,
        repo: CompanionRepository,
        llm: LLMClient,
        templates: TemplateRepository | None = None,
    ) -> None:
        self._repo = repo
        self._llm = llm
        self._templates = templates

    # ---------- 人设生成 ----------
    async def generate_persona(
        self, user_id: str, description: str, request_id: str
    ) -> tuple[Persona, LLMResult]:
        text = (description or "").strip()
        if len(text) < MIN_DESCRIPTION:
            raise InvalidInput("请再多说几个字，方便生成人设", code="DESCRIPTION_TOO_SHORT")
        if len(text) > MAX_DESCRIPTION:
            raise InvalidInput("描述太长了，请控制在 200 字以内", code="DESCRIPTION_TOO_LONG")
        context = CallContext(
            user_id=user_id, request_id=request_id, task=TaskName.PERSONA_GENERATE
        )
        result = await self._llm.complete(
            TaskName.PERSONA_GENERATE, _draft_messages(text), context=context
        )
        try:
            persona = Persona.model_validate(extract_json(result.text))
        except Exception as first_error:  # noqa: BLE001 - 统一转成修复重试
            repaired = await self._llm.complete(
                TaskName.PERSONA_GENERATE,
                _repair_messages(text, result.text, str(first_error)[:300]),
                context=context,
            )
            try:
                persona = Persona.model_validate(extract_json(repaired.text))
            except Exception as exc:  # noqa: BLE001
                raise AppError(
                    code="PERSONA_GENERATION_FAILED",
                    message="人设生成失败，请换个说法再试一次",
                    status_code=502,
                ) from exc
            return persona, repaired
        return persona, result

    # ---------- 增删改查 ----------
    async def create(
        self,
        user_id: str,
        persona: Persona,
        *,
        name: str | None = None,
        derived_from: int | None = None,
    ) -> CompanionRecord:
        if await self._repo.count(user_id) >= MAX_COMPANIONS:
            raise AppError(
                code="COMPANION_LIMIT",
                message=f"最多创建 {MAX_COMPANIONS} 个伴侣，请先删除不用的",
                status_code=409,
            )
        final_name = (name or persona.name).strip()
        if not final_name:
            raise InvalidInput("伴侣名字不能为空")
        if len(final_name) > 20:
            raise InvalidInput("伴侣名字最多 20 个字")
        record_persona = persona.model_copy(update={"name": final_name})
        return await self._repo.create(
            user_id,
            final_name,
            record_persona,
            compile_prompt(record_persona),
            derived_from=derived_from,
        )

    async def list(self, user_id: str) -> list[CompanionRecord]:
        return await self._repo.list(user_id)

    async def create_from_template(
        self, user_id: str, template_key: str, *, name: str | None = None
    ) -> CompanionRecord:
        if self._templates is None:
            raise AppError(code="TEMPLATES_UNAVAILABLE", message="模板服务不可用", status_code=503)
        template = await self._templates.get(template_key)
        if template is None:
            raise NotFound("模板不存在")
        persona = template.persona
        if name:
            persona = persona.model_copy(update={"name": name.strip()})
        return await self.create(user_id, persona)

    async def derive(
        self,
        user_id: str,
        companion_id: int,
        persona: Persona,
        *,
        name: str | None = None,
    ) -> CompanionRecord:
        """基于已有伴侣的人设创建新伴侣；不复制会话、记忆、头像与演练。"""
        source = await self.get(user_id, companion_id)
        final_name = (name or persona.name).strip() or source.name
        record = await self.create(
            user_id,
            persona.model_copy(update={"name": final_name}),
            derived_from=source.id,
        )
        return record

    async def delete(self, user_id: str, companion_id: int, confirm_name: str) -> None:
        record = await self.get(user_id, companion_id)
        if confirm_name.strip() != record.name:
            raise AppError(
                code="CONFIRM_MISMATCH",
                message="输入的名字与伴侣名字不一致，未执行删除",
                status_code=409,
            )
        if not await self._repo.soft_delete(user_id, companion_id):
            raise NotFound("伴侣不存在")

    async def set_memory_enabled(
        self, user_id: str, companion_id: int, enabled: bool
    ) -> CompanionRecord:
        if not await self._repo.set_memory_enabled(user_id, companion_id, enabled):
            raise NotFound("伴侣不存在")
        return await self.get(user_id, companion_id)

    async def set_voice(
        self, user_id: str, companion_id: int, voice_id: str | None
    ) -> CompanionRecord:
        cleaned = (voice_id or "").strip() or None
        if cleaned is not None and len(cleaned) > 128:
            raise InvalidInput("音色标识过长", code="VOICE_ID_INVALID")
        updated = await self._repo.set_voice(user_id, companion_id, cleaned)
        if updated is None:
            raise NotFound("伴侣不存在")
        return updated

    async def set_avatar(
        self, user_id: str, companion_id: int, avatar: str | None
    ) -> CompanionRecord:
        cleaned: str | None = None
        if avatar and avatar.strip():
            value = avatar.strip()
            match = AVATAR_RE.match(value)
            if match is None:
                raise InvalidInput("头像必须是 PNG/JPEG/WebP 的 data URL", code="AVATAR_INVALID")
            try:
                raw = base64.b64decode(match.group(2), validate=True)
            except Exception as exc:  # noqa: BLE001
                raise InvalidInput("头像数据损坏", code="AVATAR_INVALID") from exc
            if len(raw) > MAX_AVATAR_BYTES:
                raise InvalidInput("头像不能超过 300KB", code="AVATAR_TOO_LARGE")
            cleaned = value
        record = await self._repo.set_avatar(user_id, companion_id, cleaned)
        if record is None:
            raise NotFound("伴侣不存在")
        return record

    async def get(self, user_id: str, companion_id: int) -> CompanionRecord:
        record = await self._repo.get(user_id, companion_id)
        if record is None:
            raise NotFound("伴侣不存在")
        return record

    async def replace_persona(
        self, user_id: str, companion_id: int, persona: Persona
    ) -> CompanionRecord:
        record = await self._repo.add_version(
            user_id, companion_id, persona, compile_prompt(persona)
        )
        if record is None:
            raise NotFound("伴侣不存在")
        return record

    async def patch_dimension(
        self, user_id: str, companion_id: int, dimension: str, value: Any
    ) -> CompanionRecord:
        if dimension not in DIMENSION_KEYS:
            raise InvalidInput(f"不支持修改的维度：{dimension}", code="UNKNOWN_DIMENSION")
        current = await self.get(user_id, companion_id)
        payload = current.persona.model_dump()
        payload[dimension] = value
        try:
            persona = Persona.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise InvalidInput(f"该维度的取值不合法：{exc}", code="PERSONA_INVALID") from exc
        return await self.replace_persona(user_id, companion_id, persona)

    async def regenerate_dimension(
        self,
        user_id: str,
        companion_id: int,
        dimension: str,
        hint: str | None,
        request_id: str,
    ) -> tuple[Any, LLMResult]:
        if dimension not in DIMENSION_KEYS:
            raise InvalidInput(f"不支持重写的维度：{dimension}", code="UNKNOWN_DIMENSION")
        current = await self.get(user_id, companion_id)
        context = CallContext(
            user_id=user_id, request_id=request_id, task=TaskName.PERSONA_GENERATE
        )
        messages = [
            Message(
                role=Role.SYSTEM,
                content=(
                    '你在修改一个已有角色人设的单个维度。只输出 JSON：{"value": 新值}。'
                    "其他维度不要动，风格要与原人设一致。"
                ),
            ),
            Message(
                role=Role.USER, content=json.dumps(current.persona.model_dump(), ensure_ascii=False)
            ),
            Message(
                role=Role.USER,
                content=f"请重写 {dimension} 维度。补充要求：{hint or '更贴合原人设'}",
            ),
        ]
        result = await self._llm.complete(TaskName.PERSONA_GENERATE, messages, context=context)
        data = extract_json(result.text)
        if "value" not in data:
            raise AppError(
                code="PERSONA_GENERATION_FAILED",
                message="重写失败，模型没有返回 value",
                status_code=502,
            )
        # 用当前人设做一次整体校验，确保新值合法
        payload = current.persona.model_dump()
        payload[dimension] = data["value"]
        try:
            Persona.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                code="PERSONA_GENERATION_FAILED",
                message=f"重写结果不合法：{exc}",
                status_code=502,
            ) from exc
        return data["value"], result
