"""演练（角色扮演）：场景、运行记录、回合推进与复盘。

设计要点：
- 演练复用会话/消息表，不污染伴侣的日常对话；
- 扮演阶段严格锁在角色里，复盘阶段才跳出角色给建议；
- 回合数有上限，防止无限练习变成闲聊。
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from app.core.errors import InvalidInput, NotFound
from app.domain.chat import (
    ChatDelta,
    ChatDone,
    ChatEvent,
    ChatMeta,
    ChatRepository,
    ChatStreamer,
    MessageRecord,
    SessionRecord,
)
from app.domain.companions import CompanionService, LLMClient
from app.domain.quota import QuotaService
from app.domain.usage import CallContext, aggregate_usage
from app.infra.llm.types import Message, Role, TaskName, Usage


@dataclass(frozen=True, slots=True)
class Scenario:
    key: str
    title: str
    category: str
    role: str
    goal: str
    difficulty: int
    max_turns: int
    opening: str
    tips: str = ""


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        key="interview_screen",
        title="技术面试模拟",
        category="职场演练",
        role="面试官",
        goal="在几轮追问里把项目讲清楚，展示你的判断力",
        difficulty=3,
        max_turns=8,
        opening="你好，先做个自我介绍吧。",
        tips="用“背景-任务-行动-结果”讲项目，数字比形容词有说服力。",
    ),
    Scenario(
        key="stranger_talk",
        title="陌生人搭讪",
        category="社交演练",
        role="咖啡店里的陌生人",
        goal="自然开口、聊满几轮、不查户口",
        difficulty=2,
        max_turns=6,
        opening="（抬头看了你一眼）你也常来这家？",
        tips="从共同环境找话题，多用开放式问题，别连续提问。",
    ),
    Scenario(
        key="ask_raise",
        title="向上沟通：提加薪",
        category="职场演练",
        role="你的直属领导",
        goal="用事实和数据提出加薪，并谈成下一步",
        difficulty=3,
        max_turns=8,
        opening="坐。最近项目怎么样？",
        tips="先说结果和贡献，再说诉求；给出可核对的依据。",
    ),
    Scenario(
        key="say_no",
        title="拒绝同事加塞",
        category="职场演练",
        role="同组同事",
        goal="拒绝临时加塞，同时不破坏关系",
        difficulty=2,
        max_turns=6,
        opening="这个需求今天能帮我做一下吗？很急。",
        tips="先共情，再讲约束，最后给替代方案（时间/范围/人选）。",
    ),
    Scenario(
        key="client_push",
        title="客户催上线",
        category="社交演练",
        role="客户负责人",
        goal="在不让步底线的情况下安抚客户并给替代方案",
        difficulty=4,
        max_turns=8,
        opening="这个功能下周能上吗？不能上你让我怎么跟老板交代？",
        tips="先接情绪，再讲事实与选项，不要空口承诺。",
    ),
)


def scenario_by_key(key: str) -> Scenario | None:
    return next((item for item in SCENARIOS if item.key == key), None)


@dataclass(slots=True)
class RunRecord:
    id: int
    user_id: str
    companion_id: int
    scenario_key: str
    session_id: int
    status: str = "active"
    max_turns: int = 8
    turns_played: int = 0
    review: dict[str, object] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


class ScenarioRepository(Protocol):
    async def list(self, category: str | None = None) -> list[Scenario]: ...

    async def get(self, key: str) -> Scenario | None: ...

    async def sync(self, scenarios: tuple[Scenario, ...]) -> int: ...


class RunRepository(Protocol):
    async def create(
        self, user_id: str, companion_id: int, scenario_key: str, session_id: int, max_turns: int
    ) -> RunRecord: ...

    async def get(self, user_id: str, run_id: int) -> RunRecord | None: ...

    async def increment_turns(self, user_id: str, run_id: int) -> int: ...

    async def finish(self, user_id: str, run_id: int, review: dict[str, object]) -> None: ...


class InMemoryScenarioRepository:
    def __init__(self, scenarios: tuple[Scenario, ...]) -> None:
        self._items = {item.key: item for item in scenarios}

    async def list(self, category: str | None = None) -> list[Scenario]:
        items = list(self._items.values())
        return [item for item in items if item.category == category] if category else items

    async def get(self, key: str) -> Scenario | None:
        return self._items.get(key)

    async def sync(self, scenarios: tuple[Scenario, ...]) -> int:
        for item in scenarios:
            self._items[item.key] = item
        return len(scenarios)


class InMemoryRunRepository:
    def __init__(self) -> None:
        self.items: dict[int, RunRecord] = {}
        self._next_id = 1

    async def create(
        self, user_id: str, companion_id: int, scenario_key: str, session_id: int, max_turns: int
    ) -> RunRecord:
        record = RunRecord(
            id=self._next_id,
            user_id=user_id,
            companion_id=companion_id,
            scenario_key=scenario_key,
            session_id=session_id,
            max_turns=max_turns,
        )
        self.items[record.id] = record
        self._next_id += 1
        return record

    async def get(self, user_id: str, run_id: int) -> RunRecord | None:
        item = self.items.get(run_id)
        return item if item is not None and item.user_id == user_id else None

    async def increment_turns(self, user_id: str, run_id: int) -> int:
        item = await self.get(user_id, run_id)
        if item is None:
            return 0
        item.turns_played += 1
        if item.turns_played >= item.max_turns and item.status == "active":
            item.status = "max_reached"
        return item.turns_played

    async def finish(self, user_id: str, run_id: int, review: dict[str, object]) -> None:
        item = await self.get(user_id, run_id)
        if item is None:
            return
        item.review = review
        item.status = "finished"
        item.finished_at = datetime.now(UTC)


def roleplay_system_prompt(scenario: Scenario, turns_played: int) -> str:
    pressure = (
        "更挑剔、会打断，偶尔质疑细节" if scenario.difficulty >= 4 else "相对配合，愿意给台阶"
    )
    return (
        "# 你现在扮演\n"
        f"你是{scenario.role}，正在参与「{scenario.title}」这个场景。\n"
        f"用户的目标是：{scenario.goal}\n"
        f"难度：{scenario.difficulty}/5。\n"
        "# 规则\n"
        "- 只以角色身份说话，绝不跳出角色，不评价用户的表现，也不给建议（复盘在结束后才给）。\n"
        "- 一次回复 1–3 句，像真人一样自然，有反应、有情绪。\n"
        f"- 当前是第 {turns_played + 1} 轮，{pressure}。\n"
        "- 用户卡住时可以给一个很小的台阶，但不要替他回答。\n"
    )


def build_review_prompt(scenario: Scenario, transcript: str) -> str:
    return (
        "你是沟通教练。根据下面这场演练对话，给用户一份具体、可执行的复盘。\n"
        "只输出 JSON，不要解释、不要代码块：\n"
        '{"summary":"一句话总评","scores":{"clarity":1-5,"empathy":1-5,"structure":1-5,'
        '"confidence":1-5},"highlights":["做得好的具体点"],'
        '"improvements":["可改进的具体点"],"sample_lines":["可以这样说的示范句"]}\n'
        "要求：引用用户的原话；每条不超过 40 字；不要空泛鼓励；至少 2 条亮点和 2 条改进。\n\n"
        f"场景：{scenario.title}｜你的角色：{scenario.role}｜用户目标：{scenario.goal}\n\n"
        f"对话：\n{transcript}"
    )


def _escape_control_chars(text: str) -> str:
    """把 JSON 字符串内部的裸换行/制表符转义，兼容模型偶发的不规范输出。"""

    def fix(match: re.Match[str]) -> str:
        inner = match.group(0)
        return inner.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")

    return re.sub(r'"(?:[^"\\]|\\.)*"', fix, text)


def parse_review(text: str) -> dict[str, object]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE).strip()
    candidates = [cleaned, _escape_control_chars(cleaned)]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start >= 0 and end > start:
        chunk = cleaned[start : end + 1]
        candidates.extend([chunk, _escape_control_chars(chunk)])
    data: object = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
            break
        except json.JSONDecodeError:
            continue
    if not isinstance(data, dict):
        return {"summary": cleaned[:200], "scores": {}, "highlights": [], "improvements": []}
    scores = data.get("scores")
    clean_scores: dict[str, int] = {}
    if isinstance(scores, dict):
        for key in ("clarity", "empathy", "structure", "confidence"):
            value = scores.get(key)
            if isinstance(value, (int, float)):
                clean_scores[key] = max(1, min(5, int(value)))
    return {
        "summary": str(data.get("summary", ""))[:200],
        "scores": clean_scores,
        "highlights": [str(item)[:120] for item in data.get("highlights", [])][:5]
        if isinstance(data.get("highlights"), list)
        else [],
        "improvements": [str(item)[:120] for item in data.get("improvements", [])][:5]
        if isinstance(data.get("improvements"), list)
        else [],
        "sample_lines": [str(item)[:120] for item in data.get("sample_lines", [])][:3]
        if isinstance(data.get("sample_lines"), list)
        else [],
    }


class RoleplayService:
    def __init__(
        self,
        scenarios: ScenarioRepository,
        runs: RunRepository,
        chat: ChatRepository,
        companions: CompanionService,
        streamer: ChatStreamer,
        llm: LLMClient,
        *,
        history_limit: int = 20,
        quota: QuotaService | None = None,
        profiles: object | None = None,
    ) -> None:
        self._scenarios = scenarios
        self._runs = runs
        self._chat = chat
        self._companions = companions
        self._streamer = streamer
        self._llm = llm
        self._history_limit = history_limit
        self._quota = quota
        self._profiles = profiles

    async def ensure_quota(self, user_id: str) -> None:
        if self._quota is not None:
            await self._quota.ensure_available(user_id)

    async def list_scenarios(self, category: str | None = None) -> list[Scenario]:
        return await self._scenarios.list(category)

    async def start(
        self,
        user_id: str,
        companion_id: int,
        scenario_key: str,
        max_turns: int | None = None,
    ) -> tuple[RunRecord, SessionRecord, MessageRecord]:
        await self._companions.get(user_id, companion_id)
        scenario = await self._scenarios.get(scenario_key)
        if scenario is None:
            raise NotFound("演练场景不存在")
        session = await self._chat.create_session(user_id, companion_id, scenario.title)
        opening = await self._chat.append_message(
            user_id, session.id, "assistant", scenario.opening
        )
        run = await self._runs.create(
            user_id,
            companion_id,
            scenario_key,
            session.id,
            min(max_turns or scenario.max_turns, 20),
        )
        return run, session, opening

    async def get(self, user_id: str, run_id: int) -> RunRecord:
        run = await self._runs.get(user_id, run_id)
        if run is None:
            raise NotFound("演练不存在")
        return run

    async def stream_turn(
        self, user_id: str, run_id: int, content: str, request_id: str
    ) -> AsyncIterator[ChatEvent]:
        text = (content or "").strip()
        if not text:
            raise InvalidInput("消息不能为空")
        run = await self.get(user_id, run_id)
        if run.status == "finished":
            raise InvalidInput("这场演练已经结束，可以开始新的一场", code="ROLEPLAY_FINISHED")
        if run.turns_played >= run.max_turns:
            raise InvalidInput("已达到回合上限，请结束并查看复盘", code="ROLEPLAY_MAX_TURNS")
        scenario = await self._scenarios.get(run.scenario_key)
        if scenario is None:
            raise NotFound("演练场景不存在")

        user_message = await self._chat.append_message(user_id, run.session_id, "user", text)
        yield ChatMeta(session_id=run.session_id, user_message_id=user_message.id)

        if self._quota is not None:
            await self._quota.consume(user_id)

        history = await self._chat.list_messages(user_id, run.session_id, limit=self._history_limit)
        profile_note = ""
        if self._profiles is not None:
            try:
                profile_note = await self._profiles.prompt_for(user_id, run.companion_id)  # type: ignore[attr-defined]
            except Exception:
                profile_note = ""
        messages = [
            Message(
                role=Role.SYSTEM,
                content=profile_note + roleplay_system_prompt(scenario, run.turns_played),
            )
        ]
        for item in history:
            role = Role.ASSISTANT if item.role == "assistant" else Role.USER
            messages.append(Message(role=role, content=item.content))

        collected = ""
        usage_parts: list[Usage] = []
        model_key = ""
        try:
            async for chunk in self._streamer.stream(
                TaskName.CHAT_MAIN,
                messages,
                context=CallContext(
                    user_id=user_id, request_id=request_id, task=TaskName.CHAT_MAIN
                ),
            ):
                if chunk.model_key:
                    model_key = chunk.model_key
                if chunk.usage is not None:
                    usage_parts.append(chunk.usage)
                if chunk.delta:
                    collected += chunk.delta
                    yield ChatDelta(chunk.delta)
        except Exception:
            if collected:
                await self._chat.append_message(user_id, run.session_id, "assistant", collected)
            elif self._quota is not None:
                await self._quota.refund(user_id)
            raise

        assistant = await self._chat.append_message(user_id, run.session_id, "assistant", collected)
        await self._runs.increment_turns(user_id, run_id)
        yield ChatDone(
            assistant_message_id=assistant.id,
            model_key=model_key,
            usage=aggregate_usage(usage_parts),
        )

    async def finish(self, user_id: str, run_id: int, request_id: str) -> RunRecord:
        run = await self.get(user_id, run_id)
        if run.review:
            return run
        scenario = await self._scenarios.get(run.scenario_key)
        if scenario is None:
            raise NotFound("演练场景不存在")
        messages = await self._chat.list_messages(user_id, run.session_id, limit=40)
        transcript = "\n".join(
            f"{'用户' if item.role == 'user' else '对方'}：{item.content}" for item in messages
        )
        result = await self._llm.complete(
            TaskName.ROLEPLAY_REVIEW,
            [
                Message(
                    role=Role.SYSTEM,
                    content="你是沟通教练，只输出 JSON 复盘。",
                ),
                Message(role=Role.USER, content=build_review_prompt(scenario, transcript)),
            ],
            context=CallContext(
                user_id=user_id, request_id=request_id, task=TaskName.ROLEPLAY_REVIEW
            ),
        )
        review = parse_review(result.text)
        if not review.get("scores") and not review.get("highlights"):
            repaired = await self._llm.complete(
                TaskName.ROLEPLAY_REVIEW,
                [
                    Message(role=Role.SYSTEM, content="你是沟通教练，只输出 JSON 复盘。"),
                    Message(
                        role=Role.USER,
                        content=build_review_prompt(scenario, transcript)
                        + "\n\n注意：上一次输出无法解析为 JSON。请严格只输出一个合法的 JSON 对象，"
                        "字符串内部不要出现未转义的换行。",
                    ),
                ],
                context=CallContext(
                    user_id=user_id, request_id=request_id, task=TaskName.ROLEPLAY_REVIEW
                ),
            )
            review = parse_review(repaired.text)
        await self._runs.finish(user_id, run_id, review)
        return await self.get(user_id, run_id)

    async def messages(self, user_id: str, run_id: int) -> Sequence[MessageRecord]:
        run = await self.get(user_id, run_id)
        return await self._chat.list_messages(user_id, run.session_id, limit=100)
