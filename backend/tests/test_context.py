from app.domain.chat import MessageRecord
from app.domain.context import (
    MAX_SUMMARY_CHARS,
    build_summary_prompt,
    clamp_summary,
    plan_history,
    transcript_of,
)


def history(count: int, chars: int = 20) -> list[MessageRecord]:
    return [
        MessageRecord(
            id=index,
            session_id=1,
            seq=index,
            role="user" if index % 2 else "assistant",
            content="字" * chars,
        )
        for index in range(1, count + 1)
    ]


def test_plan_keeps_recent_and_flags_older() -> None:
    plan = plan_history(history(10), system_tokens=100, budget_tokens=200)
    assert plan.older, "预算不足时应有旧消息被移出"
    assert plan.kept[-1].seq == 10
    assert len(plan.kept) >= 4
    assert plan.older[-1].seq < plan.kept[0].seq


def test_plan_keeps_everything_when_budget_is_large() -> None:
    plan = plan_history(history(5), system_tokens=10, budget_tokens=100_000)
    assert plan.older == []
    assert len(plan.kept) == 5


def test_plan_always_keeps_last_four_when_budget_tiny() -> None:
    plan = plan_history(history(10), system_tokens=500, budget_tokens=100)
    assert len(plan.kept) == 4
    assert [item.seq for item in plan.kept] == [7, 8, 9, 10]
    assert len(plan.older) == 6


def test_plan_handles_empty_history() -> None:
    plan = plan_history([], system_tokens=10, budget_tokens=100)
    assert plan.kept == []
    assert plan.older == []


def test_clamp_summary_limits_length() -> None:
    long_text = "很长的摘要" * 100
    clamped = clamp_summary(long_text)
    assert len(clamped) <= MAX_SUMMARY_CHARS
    assert clamped.endswith("…")


def test_clamp_summary_collapses_whitespace() -> None:
    assert clamp_summary("  第一句\n\n第二句  ") == "第一句 第二句"


def test_transcript_labels_speakers() -> None:
    text = transcript_of(history(2, chars=5))
    assert "用户：" in text
    assert "伴侣：" in text


def test_transcript_truncates_long_input() -> None:
    messages = [
        MessageRecord(id=1, session_id=1, seq=1, role="user", content="长" * 300) for _ in range(10)
    ]
    text = transcript_of(messages, max_chars=200)
    assert "…" in text


def test_summary_prompt_mentions_previous_summary() -> None:
    prompt = build_summary_prompt("用户：你好", "之前的摘要")
    assert "之前的摘要" in prompt
    assert "不超过 200 字" in prompt
