"""上下文组装：预算裁剪 + 早期对话摘要。

规则：
- 最近的消息优先保留；系统提示（人设/安全/记忆）不计入可裁剪范围；
- 超出预算时，从最旧的消息开始移出，交给摘要；
- 至少保留最近 4 条原文，避免刚说的话被摘要掉；
- 摘要只在「有新的旧消息」时重算，覆盖范围记录在 covered_seq。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.infra.llm.tokenizer import estimate_tokens

MAX_SUMMARY_CHARS = 240
KEEP_LAST_ALWAYS = 4
MESSAGE_OVERHEAD = 4


class HistoryItem(Protocol):
    seq: int
    role: str
    content: str


@dataclass(slots=True)
class ContextPlan:
    kept: list[HistoryItem]
    older: list[HistoryItem]


def plan_history(
    history: Sequence[HistoryItem],
    *,
    system_tokens: int,
    budget_tokens: int,
    keep_last: int = KEEP_LAST_ALWAYS,
) -> ContextPlan:
    """把历史切成「保留原文」与「需要摘要」两段。"""
    if budget_tokens <= system_tokens:
        keep = max(keep_last, 1)
        kept = list(history[-keep:]) if history else []
        older = list(history[:-keep]) if len(history) > keep else []
        return ContextPlan(kept=kept, older=older)
    used = system_tokens
    kept_reversed: list[HistoryItem] = []
    for index, item in enumerate(reversed(history)):
        cost = MESSAGE_OVERHEAD + estimate_tokens(item.content)
        if index >= keep_last and used + cost > budget_tokens:
            break
        kept_reversed.append(item)
        used += cost
    kept = list(reversed(kept_reversed))
    older = list(history[: len(history) - len(kept)])
    return ContextPlan(kept=kept, older=older)


def build_summary_prompt(transcript: str, previous_summary: str | None) -> str:
    previous = previous_summary or "（无）"
    return (
        "请把下面这段较早的对话压缩成不超过 200 字的摘要，供以后继续聊天时参考。\n"
        "必须保留：用户的处境与重要事件、情绪状态、做过的决定、约定与时间点、边界与雷区。\n"
        "可以丢弃：寒暄、重复内容、无信息量的客套。\n"
        "不要编造，不要评价，不要用列表。\n\n"
        f"已有摘要：{previous}\n\n"
        f"对话：\n{transcript}"
    )


def transcript_of(messages: Sequence[HistoryItem], *, max_chars: int = 6000) -> str:
    lines: list[str] = []
    total = 0
    for item in messages:
        label = "用户" if item.role == "user" else "伴侣"
        line = f"{label}：{item.content}"
        if total + len(line) > max_chars:
            lines.append(f"{label}：{item.content[:120]}…")
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


def clamp_summary(text: str) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= MAX_SUMMARY_CHARS:
        return cleaned
    return cleaned[: MAX_SUMMARY_CHARS - 1] + "…"
