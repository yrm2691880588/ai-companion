from app.infra.llm.tokenizer import (
    estimate_messages_tokens,
    estimate_tokens,
    fit_messages,
    truncate_tokens,
)
from app.infra.llm.types import Message, Role


def test_empty_text_costs_nothing() -> None:
    assert estimate_tokens("") == 0


def test_chinese_is_roughly_065_token_per_char() -> None:
    assert estimate_tokens("你好") == 2  # ceil(2 * 0.65)
    assert 60 <= estimate_tokens("一" * 100) <= 70


def test_ascii_costs_less_per_char() -> None:
    assert estimate_tokens("hello world") < len("hello world")


def test_estimate_is_monotonic() -> None:
    short = estimate_tokens("今天有点累")
    long = estimate_tokens("今天有点累，想找个人说说话，明天还要面试")
    assert long > short


def test_messages_overhead_counts_system_and_reply() -> None:
    messages = [
        Message(role=Role.SYSTEM, content="你是学姐"),
        Message(role=Role.USER, content="你好"),
    ]
    expected = estimate_tokens("你是学姐") + estimate_tokens("你好")
    assert estimate_messages_tokens(messages) > expected


def test_fit_messages_keeps_newest_and_system() -> None:
    messages = [
        Message(role=Role.SYSTEM, content="人设指令"),
        Message(role=Role.USER, content="旧" * 500),
        Message(role=Role.ASSISTANT, content="旧回复" * 50),
        Message(role=Role.USER, content="最新一句"),
    ]
    fitted = fit_messages(messages, 120)
    assert fitted[0].role is Role.SYSTEM
    assert fitted[-1].content == "最新一句"
    assert estimate_messages_tokens(fitted) <= 120


def test_fit_messages_zero_budget_returns_empty() -> None:
    assert fit_messages([Message(role=Role.USER, content="hi")], 0) == []


def test_truncate_keeps_tail_within_budget() -> None:
    text = "很长的开头" * 100 + "结尾重点"
    truncated = truncate_tokens(text, 20)
    assert truncated.endswith("结尾重点")
    assert estimate_tokens(truncated) <= 20


def test_truncate_noop_when_fits() -> None:
    assert truncate_tokens("短句", 100) == "短句"
