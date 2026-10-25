"""Token 估算：本地只做保守估算，账单以供应商返回的 usage 为准。

中文按「1 token ≈ 1.5–1.7 个汉字」、ASCII 按「1 token ≈ 3.5 个字符」估算，
并保留每条消息 4 token 的模板开销（与 OpenAI 兼容接口的常见口径一致）。
"""

from __future__ import annotations

from collections.abc import Sequence
from math import ceil

from app.infra.llm.types import Message, Role

CJK_PER_TOKEN = 0.65  # 1 个汉字 ≈ 0.65 token
ASCII_CHARS_PER_TOKEN = 3.5
MESSAGE_OVERHEAD = 4
REPLY_PRIMING = 3


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF  # 基本汉字
        or 0x3400 <= code <= 0x4DBF  # 扩展 A
        or 0x3000 <= code <= 0x303F  # 中文标点
        or 0xFF00 <= code <= 0xFFEF  # 全角符号
    )


def estimate_tokens(text: str) -> int:
    """估算一段文本的 token 数（至少为 0）。"""
    if not text:
        return 0
    cjk = sum(1 for char in text if _is_cjk(char))
    other = len(text) - cjk
    total = cjk * CJK_PER_TOKEN + other / ASCII_CHARS_PER_TOKEN
    return max(1, ceil(total))


def estimate_messages_tokens(messages: Sequence[Message]) -> int:
    """估算整段请求的输入 token。"""
    total = REPLY_PRIMING
    for message in messages:
        total += MESSAGE_OVERHEAD + estimate_tokens(message.content)
    return total


def truncate_tokens(text: str, max_tokens: int) -> str:
    """从开头裁掉内容，保留尾部（最新的话更重要）。"""
    if max_tokens <= 0:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text
    low, high = 0, len(text)
    while low < high:
        mid = (low + high) // 2
        if estimate_tokens(text[mid:]) <= max_tokens:
            high = mid
        else:
            low = mid + 1
    return text[low:]


def fit_messages(
    messages: Sequence[Message],
    budget_tokens: int,
    *,
    keep_system: bool = True,
) -> list[Message]:
    """把消息裁剪到预算内：系统消息优先保留，对话从旧到新丢弃。"""
    if budget_tokens <= 0:
        return []
    systems = [m for m in messages if m.role is Role.SYSTEM] if keep_system else []
    dialogue = [m for m in messages if m.role is not Role.SYSTEM]
    used = estimate_messages_tokens(systems)
    kept_reversed: list[Message] = []
    for message in reversed(dialogue):
        cost = MESSAGE_OVERHEAD + estimate_tokens(message.content)
        if used + cost > budget_tokens and kept_reversed:
            break
        if used + cost > budget_tokens:
            kept_reversed.append(message)
            break
        kept_reversed.append(message)
        used += cost
    kept = list(reversed(kept_reversed))
    if kept and used > budget_tokens:
        last = kept[-1]
        remain = max(budget_tokens - estimate_messages_tokens(systems) - MESSAGE_OVERHEAD, 16)
        kept = [Message(role=last.role, content=truncate_tokens(last.content, remain))]
    return systems + kept
