import json

import pytest

from app.core.errors import InvalidInput
from app.domain.memory import (
    TYPE_LABELS,
    InMemoryMemoryRepository,
    MemoryService,
    MemoryType,
    format_for_prompt,
    is_sensitive,
    normalize_content,
    overlap_ratio,
    parse_items,
)
from app.domain.usage import CallContext


class FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    async def complete(self, task, messages, *, context: CallContext):
        self.calls += 1
        text = self.responses.pop(0)

        class Result:
            pass

        result = Result()
        result.text = text
        result.model_key = "fake:model"
        result.usage = None
        result.cost_cny = 0
        return result


def payload(*items: dict[str, object]) -> str:
    return json.dumps({"items": list(items)}, ensure_ascii=False)


async def test_extract_creates_valid_items() -> None:
    llm = FakeLLM(
        [
            payload(
                {
                    "type": "promise",
                    "content": "下周五要去字节面试",
                    "confidence": 0.9,
                    "quote": "我下周五要去字节面试",
                },
                {
                    "type": "preference",
                    "content": "喜欢喝冰美式",
                    "confidence": 0.8,
                    "quote": "我一般喝冰美式",
                },
            )
        ]
    )
    repo = InMemoryMemoryRepository()
    service = MemoryService(repo, llm)
    created = await service.extract("u1", 1, 1, [("user", "我下周五要去字节面试")], "r1")
    assert len(created) == 2
    assert created[0].type == "promise"
    assert created[0].confidence == 0.9


async def test_extract_dedupes_same_content() -> None:
    text = payload({"type": "habit", "content": "习惯凌晨两点睡", "confidence": 0.9})
    repo = InMemoryMemoryRepository()
    service = MemoryService(repo, FakeLLM([text, text]))
    await service.extract("u1", 1, 1, [("user", "我每天两点才睡")], "r1")
    second = await service.extract("u1", 1, 2, [("user", "我每天两点才睡")], "r2")
    assert second == []


async def test_extract_dedupes_near_duplicates() -> None:
    first = payload({"type": "promise", "content": "下周五要去字节面试", "confidence": 0.9})
    second = payload(
        {"type": "promise", "content": "用户下周五要去字节跳动面试", "confidence": 0.9}
    )
    repo = InMemoryMemoryRepository()
    service = MemoryService(repo, FakeLLM([first, second]))
    await service.extract("u1", 1, 1, [("user", "下周五要去字节面试")], "r1")
    created = await service.extract("u1", 1, 2, [("user", "下周五要去字节跳动面试")], "r2")
    assert created == []


async def test_extract_skips_sensitive_without_remember() -> None:
    llm = FakeLLM(
        [
            payload(
                {
                    "type": "experience",
                    "content": "住在朝阳区某小区",
                    "confidence": 0.9,
                    "quote": "我住在朝阳区",
                }
            )
        ]
    )
    service = MemoryService(InMemoryMemoryRepository(), llm)
    created = await service.extract("u1", 1, 1, [("user", "我住在朝阳区")], "r1")
    assert created == []


async def test_extract_keeps_sensitive_when_user_says_remember() -> None:
    llm = FakeLLM(
        [
            payload(
                {
                    "type": "experience",
                    "content": "住在朝阳区",
                    "confidence": 0.9,
                    "quote": "记住，我住在朝阳区",
                }
            )
        ]
    )
    service = MemoryService(InMemoryMemoryRepository(), llm)
    created = await service.extract("u1", 1, 1, [("user", "记住，我住在朝阳区")], "r1")
    assert len(created) == 1


async def test_extract_drops_invalid_type_and_low_confidence() -> None:
    llm = FakeLLM(
        [
            payload(
                {"type": "unknown", "content": "很长的内容", "confidence": 0.9},
                {"type": "habit", "content": "每天跑步", "confidence": 0.2},
            )
        ]
    )
    service = MemoryService(InMemoryMemoryRepository(), llm)
    assert await service.extract("u1", 1, 1, [("user", "每天跑步")], "r1") == []


async def test_extract_returns_empty_on_bad_json() -> None:
    service = MemoryService(InMemoryMemoryRepository(), FakeLLM(["不是 JSON"]))
    assert await service.extract("u1", 1, 1, [("user", "随便说说")], "r1") == []


async def test_recall_prefers_promise_and_overlap() -> None:
    repo = InMemoryMemoryRepository()
    service = MemoryService(repo, FakeLLM([]))
    await repo.add(
        "u1",
        1,
        type="preference",
        content="喜欢喝冰美式",
        confidence=0.8,
        quote=None,
        source_session_id=1,
        source_message_id=None,
    )
    promise = await repo.add(
        "u1",
        1,
        type="promise",
        content="下周五要去字节面试",
        confidence=0.9,
        quote=None,
        source_session_id=1,
        source_message_id=None,
    )
    recalled = await service.recall("u1", 1, "明天面试要准备什么", limit=5)
    assert recalled[0].id == promise.id
    assert any(item.type == "preference" for item in recalled)


async def test_recall_is_isolated_between_companions() -> None:
    repo = InMemoryMemoryRepository()
    service = MemoryService(repo, FakeLLM([]))
    await repo.add(
        "u1",
        1,
        type="promise",
        content="下周五面试",
        confidence=0.9,
        quote=None,
        source_session_id=1,
        source_message_id=None,
    )
    assert await service.recall("u1", 2, "面试") == []


async def test_delete_removes_from_active_list() -> None:
    repo = InMemoryMemoryRepository()
    service = MemoryService(repo, FakeLLM([]))
    item = await repo.add(
        "u1",
        1,
        type="habit",
        content="每天跑步",
        confidence=0.8,
        quote=None,
        source_session_id=1,
        source_message_id=None,
    )
    await service.delete("u1", item.id)
    assert await service.list("u1", 1) == []


async def test_list_rejects_unknown_type() -> None:
    service = MemoryService(InMemoryMemoryRepository(), FakeLLM([]))
    with pytest.raises(InvalidInput):
        await service.list("u1", 1, type="unknown")


def test_format_for_prompt_includes_labels() -> None:
    from app.domain.memory import MemoryRecord

    block = format_for_prompt(
        [
            MemoryRecord(
                id=1,
                user_id="u1",
                companion_id=1,
                type="promise",
                content="下周五面试",
            )
        ]
    )
    assert "# 你记得的事" in block
    assert f"[{TYPE_LABELS[MemoryType.PROMISE]}] 下周五面试" in block


def test_helpers() -> None:
    assert normalize_content("我 喜欢，冰美式。") == "我喜欢冰美式"
    assert overlap_ratio("明天面试", "下周五要去字节面试") > 0
    assert is_sensitive("我住在朝阳区", None) is True
    assert is_sensitive("我住在朝阳区", "记住这个") is False


def test_parse_items_requires_items_array() -> None:
    with pytest.raises(InvalidInput):
        parse_items('{"items": "not-a-list"}')
