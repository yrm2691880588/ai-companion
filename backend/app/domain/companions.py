"""伴侣（Companion）：人设版本、创建与编辑的领域服务。

约束：
- 单账号最多 10 个伴侣；
- 每次改人设生成新版本（不覆盖历史），只影响之后的回复；
- 生成人设走 persona_generate 任务，失败自动修复一次，仍失败则报错。
"""

from __future__ import annotations

import base64
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from app.core.errors import AppError, InvalidInput, NotFound
from app.core.ids import new_ulid
from app.domain.persona import (
    DIMENSION_KEYS,
    REFINABLE_DIMENSIONS,
    Persona,
    compile_prompt,
)
from app.domain.templates import TemplateRepository
from app.domain.usage import CallContext
from app.infra.llm.types import Message, Role, TaskName, Usage

logger = logging.getLogger(__name__)

MAX_COMPANIONS = 50
MIN_DESCRIPTION = 4
MAX_DESCRIPTION = 200
# 单维 AI 改写时用户补充要求的长度上限。
# 一句话说清就行，写太长反而会让模型抓不住重点，也多花钱。
MAX_REFINE_HINT = 200
# 每个伴侣保留多少个历史人设版本。
# 每次保存都会新增一行，不设上限会无限增长；20 个足够回退到任意近期的改动。
MAX_PERSONA_VERSIONS = 20
MAX_AVATAR_BYTES = 300 * 1024
# 批量删除：一次最多删多少个，以及必须手输的确认词。
# 规则放这里是因为它属于业务约束，api 层只做协议映射。
MAX_BATCH_DELETE = 50
BATCH_DELETE_CONFIRM = "删除"
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
    ulid: str = ""


@dataclass(slots=True)
class PersonaVersionRecord:
    """人设的一个历史版本。

    每次保存人设都会新增一行；这里只带「能展示和还原」需要的字段，
    不返回 compiled_prompt（体积大，界面也用不到）。
    """

    version: int
    persona: Persona
    created_at: datetime


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
        ulid: str | None = None,
    ) -> CompanionRecord: ...

    async def list(self, user_id: str) -> list[CompanionRecord]: ...

    async def get(self, user_id: str, companion_id: int) -> CompanionRecord | None: ...

    async def find_by_ulid(self, user_id: str, ulid: str) -> CompanionRecord | None: ...

    async def add_version(
        self, user_id: str, companion_id: int, persona: Persona, compiled_prompt: str
    ) -> CompanionRecord | None: ...

    async def list_versions(
        self, user_id: str, companion_id: int
    ) -> list[PersonaVersionRecord]: ...

    async def get_version(
        self, user_id: str, companion_id: int, version: int
    ) -> PersonaVersionRecord | None: ...

    async def prune_versions(
        self, user_id: str, companion_id: int, keep: int
    ) -> int: ...

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
        # 内存里的人设版本历史：companion_id → [PersonaVersionRecord]
        self._versions: dict[int, list[PersonaVersionRecord]] = {}

    async def count(self, user_id: str) -> int:
        return sum(1 for item in self._items.values() if item.user_id == user_id)

    async def create(
        self,
        user_id: str,
        name: str,
        persona: Persona,
        compiled_prompt: str,
        derived_from: int | None = None,
        ulid: str | None = None,
    ) -> CompanionRecord:
        record = CompanionRecord(
            id=self._next_id,
            user_id=user_id,
            name=name,
            current_version=1,
            persona=persona,
            compiled_prompt=compiled_prompt,
            derived_from=derived_from,
            ulid=ulid or new_ulid(),
        )
        self._items[record.id] = record
        # 创建即 v1：历史列表里要有起点，否则「还原到最初」无从下手
        self._versions[record.id] = [
            PersonaVersionRecord(
                version=1, persona=persona, created_at=datetime.now(UTC)
            )
        ]
        self._next_id += 1
        return record

    async def find_by_ulid(self, user_id: str, ulid: str) -> CompanionRecord | None:
        cleaned = (ulid or "").strip()
        if not cleaned:
            return None
        for item in self._items.values():
            if item.user_id == user_id and item.ulid == cleaned:
                return item
        return None

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
        # 内存版也要留历史：否则版本列表在测试里永远是空的
        self._versions.setdefault(companion_id, []).append(
            PersonaVersionRecord(
                version=item.current_version, persona=persona, created_at=datetime.now(UTC)
            )
        )
        return item

    async def list_versions(
        self, user_id: str, companion_id: int
    ) -> list[PersonaVersionRecord]:
        if await self.get(user_id, companion_id) is None:
            return []
        return sorted(
            self._versions.get(companion_id, []), key=lambda v: v.version, reverse=True
        )

    async def get_version(
        self, user_id: str, companion_id: int, version: int
    ) -> PersonaVersionRecord | None:
        if await self.get(user_id, companion_id) is None:
            return None
        for item in self._versions.get(companion_id, []):
            if item.version == version:
                return item
        return None

    async def prune_versions(self, user_id: str, companion_id: int, keep: int) -> int:
        if keep < 1 or await self.get(user_id, companion_id) is None:
            return 0
        items = sorted(self._versions.get(companion_id, []), key=lambda v: v.version, reverse=True)
        if len(items) <= keep:
            return 0
        self._versions[companion_id] = items[:keep]
        return len(items) - keep

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


def _single_dimension_messages(
    persona: Persona, dimension: str, hint: str | None, *, style: str
) -> list[Message]:
    """拼「重写单个维度」的提示词。

    两个调用方（已落库的伴侣 / 前端传来的草稿）的差别只在措辞，
    规则完全一致，所以提示词在这里统一构造。
    """
    current = persona.model_dump()
    return [
        Message(
            role=Role.SYSTEM,
            content=(
                "你在修改一个已有角色人设的单个维度。只输出 JSON："
                '{"value": 新值}，不要输出解释。'
                "要求：\n"
                "1. 只改被点名的那个维度，其他维度一律不动；\n"
                "2. 写作风格、人称、详略要与原人设保持一致；\n"
                "3. 类型要和原值相同（列表就是列表，字符串就是字符串）；\n"
                "4. 不要引入和原人设矛盾的信息。"
                f"\n补充说明：{style}"
            ),
        ),
        Message(
            role=Role.USER,
            content=(
                "当前人设（JSON）：\n"
                f"{json.dumps(current, ensure_ascii=False)}\n\n"
                f"要调整的维度：{dimension}\n"
                f"该维度当前值：{json.dumps(current.get(dimension), ensure_ascii=False)}\n"
                f"用户的要求：{hint or '更贴合原人设'}"
            ),
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
        ulid: str | None = None,
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
            ulid=ulid,
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

    async def delete_for_batch(
        self, user_id: str, companion_id: int, confirm: str
    ) -> CompanionRecord:
        """批量删除单个：用确认词代替「输入名字」。

        为什么不直接调 delete(record.name)：那等于让服务端自己填答案，
        确认校验退化为空实现。这里显式要求确认词，语义与单删一致——
        只是确认凭据从「名字」换成「固定短语」。

        返回被删记录，调用方需要它的 id 排队硬清。
        """
        if confirm.strip() != BATCH_DELETE_CONFIRM:
            raise AppError(
                code="CONFIRM_MISMATCH",
                message=f"确认词不正确，请输入「{BATCH_DELETE_CONFIRM}」",
                status_code=409,
            )
        record = await self.get(user_id, companion_id)
        if not await self._repo.soft_delete(user_id, companion_id):
            raise NotFound("伴侣不存在")
        return record

    def check_batch_delete(self, ids: list[int], confirm: str) -> list[int]:
        """批量删除的前置校验：确认词与数量上限。

        返回去重后的 id 列表。规则属于业务约束，放在 domain 层；
        api 层只负责把请求转成参数。
        """
        if confirm.strip() != BATCH_DELETE_CONFIRM:
            raise InvalidInput(
                f"确认词不正确，请输入「{BATCH_DELETE_CONFIRM}」", code="CONFIRM_MISMATCH"
            )
        if not ids:
            raise InvalidInput("没有选中任何伴侣", code="BATCH_EMPTY")
        if len(ids) > MAX_BATCH_DELETE:
            raise InvalidInput(
                f"一次最多删除 {MAX_BATCH_DELETE} 个，请分批操作",
                code="BATCH_TOO_MANY",
            )
        # 去重，避免同一个 id 重复删除导致第二次报「不存在」
        return list(dict.fromkeys(ids))

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
        # 版本不无限增长：只保留最近 MAX_PERSONA_VERSIONS 个。
        #
        # 清理失败不能影响保存本身：add_version 已经提交，用户要的人设已经生效。
        # 清理只是「顺手收垃圾」，失败了下次保存再清也一样，
        # 但若让它把异常抛出去，用户会看到「保存失败」而实际已保存，反而更糟。
        try:
            await self._repo.prune_versions(user_id, companion_id, MAX_PERSONA_VERSIONS)
        except Exception:  # noqa: BLE001
            logger.warning(
                "人设版本清理失败，不影响保存：companion=%s", companion_id, exc_info=True
            )
        return record

    async def list_persona_versions(
        self, user_id: str, companion_id: int
    ) -> list[PersonaVersionRecord]:
        """历史人设，最新的在前。"""
        await self.get(user_id, companion_id)  # 校验归属，不存在会抛 NotFound
        return await self._repo.list_versions(user_id, companion_id)

    async def restore_persona_version(
        self, user_id: str, companion_id: int, version: int
    ) -> CompanionRecord:
        """把某个历史版本的内容还原成一个**新版本**。

        为什么不直接把 current_version 改回去：
        那样会丢弃之后的版本，用户一旦还原就再也回不到「还原前」的状态。
        复制成新版本后，还原本身也是可撤销的。
        """
        target = await self._repo.get_version(user_id, companion_id, version)
        if target is None:
            raise NotFound("这个版本不存在")
        return await self.replace_persona(user_id, companion_id, target.persona)

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

    async def _rewrite_dimension(
        self,
        *,
        user_id: str,
        persona: Persona,
        dimension: str,
        hint: str | None,
        request_id: str,
        error_prefix: str,
        style: str,
    ) -> tuple[Any, LLMResult]:
        """让 AI 重写人设里的一个维度，返回建议值（不落库）。

        这是 regenerate_dimension 与 refine_draft_dimension 的共同内核。
        两者只在「人设从哪来」和少量措辞上不同，其余流程（拼提示词、调模型、
        取 JSON、用整份人设校验、错误归一）完全一致，所以抽到这里。

        为什么要抽：以后调整「AI 改写人设」的规则（换提示词、加约束、
        改错误文案），只改这一处，不会出现两条路径行为不一致。
        """
        context = CallContext(
            user_id=user_id, request_id=request_id, task=TaskName.PERSONA_GENERATE
        )
        messages = _single_dimension_messages(persona, dimension, hint, style=style)
        result = await self._llm.complete(TaskName.PERSONA_GENERATE, messages, context=context)
        data = extract_json(result.text)
        if "value" not in data:
            raise AppError(
                code="PERSONA_GENERATION_FAILED",
                message=f"{error_prefix}，换个说法再试一次",
                status_code=502,
            )

        # 用整份人设做一次校验：新值单独合法，不代表拼进去也合法
        payload = persona.model_dump()
        payload[dimension] = data["value"]
        try:
            Persona.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            raise AppError(
                code="PERSONA_GENERATION_FAILED",
                message=f"生成的内容不符合字段要求：{exc}",
                status_code=502,
            ) from exc
        return data["value"], result

    async def regenerate_dimension(
        self,
        user_id: str,
        companion_id: int,
        dimension: str,
        hint: str | None,
        request_id: str,
    ) -> tuple[Any, LLMResult]:
        """重写**已落库**伴侣的某个维度，返回建议值（不落库）。"""
        if dimension not in DIMENSION_KEYS:
            raise InvalidInput(f"不支持重写的维度：{dimension}", code="UNKNOWN_DIMENSION")
        current = await self.get(user_id, companion_id)
        return await self._rewrite_dimension(
            user_id=user_id,
            persona=current.persona,
            dimension=dimension,
            hint=hint,
            request_id=request_id,
            error_prefix="重写失败",
            style="参考的是这个伴侣当前已保存的人设。",
        )

    async def refine_draft_dimension(
        self,
        user_id: str,
        persona: Persona,
        dimension: str,
        hint: str | None,
        request_id: str,
    ) -> tuple[Any, LLMResult]:
        """按用户的自然语言要求，重写人设草稿里的某一个维度。

        与 regenerate_dimension 的区别（重要）：

        - regenerate_dimension 要求伴侣**已经落库**，因为它先按 id 查当前人设；
        - 这个方法接受**前端传入的草稿**，不查库、不落库，只返回建议值。

        为什么要这样：创建流程里伴侣还不存在，没有 id 可查；而且草稿在用户
        确认前不应写进正式库。用户点「采用」后由前端把新值写回表单，
        真正保存发生在创建伴侣那一刻。
        """
        if dimension not in DIMENSION_KEYS:
            raise InvalidInput(f"不支持重写的维度：{dimension}", code="UNKNOWN_DIMENSION")
        if dimension not in REFINABLE_DIMENSIONS:
            # 名单来自 DIMENSION_META 的 refinable 标记，不再手写第二份清单
            raise InvalidInput("这个字段不支持 AI 改写", code="DIMENSION_NOT_REFINABLE")

        cleaned_hint = (hint or "").strip()
        if len(cleaned_hint) > MAX_REFINE_HINT:
            raise InvalidInput(
                f"要求太长了，请控制在 {MAX_REFINE_HINT} 字以内",
                code="REFINE_HINT_TOO_LONG",
            )

        return await self._rewrite_dimension(
            user_id=user_id,
            persona=persona,
            dimension=dimension,
            hint=cleaned_hint,
            request_id=request_id,
            error_prefix="没生成出来",
            style="参考的是用户正在编辑、尚未保存的人设草稿。",
        )
