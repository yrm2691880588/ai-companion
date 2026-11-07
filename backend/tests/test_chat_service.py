from decimal import Decimal

import pytest

from app.core.errors import AppError, InvalidInput
from app.domain.chat import ChatDelta, ChatDone, ChatMeta, ChatService, InMemoryChatRepository
from app.domain.companions import CompanionService, InMemoryCompanionRepository, LLMResult
from app.domain.persona import Persona
from app.domain.usage import CallContext
from app.infra.llm.types import ChatChunk, Usage

PERSONA = Persona.model_validate(
    {
        "name": "林夏",
        "identity": "心理学研究生",
        "gender": "女",
        "age": 24,
        "personality": ["温柔", "偶尔毒舌"],
        "speaking_style": "句子短，先共情再给建议。",
        "background": "在读心理学研究生，晚上在便利店兼职，见过很多深夜的人。",
        "tags": ["温柔", "学姐"],
        "relationship": "住在隔壁的学姐",
    }
)


class FakeLLM:
    async def complete(self, task, messages, *, context: CallContext) -> LLMResult:
        return LLMResult("{}", "fake:model", Usage(), Decimal("0"))


class FakeStreamer:
    def __init__(self, chunks: list[ChatChunk], error: Exception | None = None) -> None:
        self.chunks = chunks
        self.error = error
        self.calls: list[list[object]] = []

    async def stream(self, task, messages, *, telemetry=None, context=None):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        for chunk in self.chunks:
            yield chunk
        if self.error is not None:
            raise self.error


async def make_service(
    chunks: list[ChatChunk] | None = None, error: Exception | None = None
) -> tuple[ChatService, InMemoryChatRepository, InMemoryCompanionRepository, int, int]:
    companions = InMemoryCompanionRepository()
    companion_service = CompanionService(companions, FakeLLM())
    record = await companion_service.create("u1", PERSONA)
    repo = InMemoryChatRepository()
    streamer = FakeStreamer(chunks or [ChatChunk(delta="嗯")], error)
    service = ChatService(repo, companion_service, streamer)
    session = await service.create_session("u1", record.id)
    return service, repo, companions, record.id, session.id


async def collect(service: ChatService, session_id: int, text: str, request_id: str = "r1"):
    return [event async for event in service.stream_reply("u1", session_id, text, request_id)]


async def test_stream_reply_emits_meta_delta_done() -> None:
    chunks = [
        ChatChunk(delta="今天", model_key="deepseek:deepseek-flash"),
        ChatChunk(delta="辛苦啦", usage=Usage(prompt_tokens=100, completion_tokens=4)),
    ]
    service, repo, _, _, session_id = await make_service(chunks)
    events = await collect(service, session_id, "我回来了")
    assert isinstance(events[0], ChatMeta)
    assert [event.text for event in events if isinstance(event, ChatDelta)] == ["今天", "辛苦啦"]
    done = events[-1]
    assert isinstance(done, ChatDone)
    assert done.assistant_message_id > 0

    messages = await repo.list_messages("u1", session_id)
    assert [item.role for item in messages] == ["user", "assistant"]
    assert messages[1].content == "今天辛苦啦"


async def test_system_prompt_contains_persona_and_safety() -> None:
    service, _, _, _, session_id = await make_service()
    streamer = service._streamer  # type: ignore[attr-defined]
    await collect(service, session_id, "在吗")
    system = streamer.calls[0][0]
    assert system.role.value == "system"
    assert "林夏" in system.content
    assert "安全与边界" in system.content


async def test_second_turn_includes_history() -> None:
    service, _, _, _, session_id = await make_service()
    streamer = service._streamer  # type: ignore[attr-defined]
    await collect(service, session_id, "第一句")
    await collect(service, session_id, "第二句", request_id="r2")
    second_call = streamer.calls[1]
    contents = [message.content for message in second_call]
    assert "第一句" in contents
    assert "嗯" in contents
    assert "第二句" in contents


async def test_partial_output_is_saved_on_failure() -> None:
    service, repo, _, _, session_id = await make_service(
        [ChatChunk(delta="说到一半")], error=RuntimeError("boom")
    )
    with pytest.raises(RuntimeError):
        await collect(service, session_id, "你好")
    messages = await repo.list_messages("u1", session_id)
    assert [item.role for item in messages] == ["user", "assistant"]
    assert messages[1].content == "说到一半"


async def test_empty_message_is_rejected() -> None:
    service, _, _, _, session_id = await make_service()
    with pytest.raises(InvalidInput):
        await collect(service, session_id, "   ")


async def test_duplicate_client_request_id_is_rejected() -> None:
    service, _, _, _, session_id = await make_service()
    await service._repo.append_message("u1", session_id, "user", "第一次", "req-abc")
    with pytest.raises(AppError) as excinfo:
        await service.stream_reply(
            "u1", session_id, "重复", "r1", client_request_id="req-abc"
        ).__anext__()
    assert excinfo.value.code == "DUPLICATE_REQUEST"


async def test_other_user_cannot_access_session() -> None:
    service, _, _, _, session_id = await make_service()
    with pytest.raises(AppError):
        await service.get_session("u2", session_id)


async def test_delete_session_hides_it() -> None:
    service, _, _, _, session_id = await make_service()
    await service.delete_session("u1", session_id)
    with pytest.raises(AppError):
        await service.get_session("u1", session_id)


# ---------- 幂等重试：同一个 client_request_id 再来一次 ----------


async def test_retry_after_complete_reply_returns_existing_reply() -> None:
    """情况 a：上次已经生成完回复，重试应原样补发，不重新调模型。"""
    service, repo, _, _, session_id = await make_service([ChatChunk(delta="已经生成好的回复")])
    first = await collect(service, session_id, "你好", "r1")
    assert any(isinstance(e, ChatDelta) for e in first)

    # 先按正常路径发一次带 request_id 的
    repo_messages_before = len(repo.messages.get(session_id, []))
    events1 = [
        event
        async for event in service.stream_reply(
            "u1", session_id, "重试测试", "r3", client_request_id="retry-req"
        )
    ]
    assert any(isinstance(e, ChatDelta) for e in events1)
    calls_after_first = len(service._streamer.calls)  # type: ignore[attr-defined]

    # 重试：应拿到同样的回复，且不再调用模型
    events2 = [
        event
        async for event in service.stream_reply(
            "u1", session_id, "重试测试", "r4", client_request_id="retry-req"
        )
    ]
    deltas2 = [e.text for e in events2 if isinstance(e, ChatDelta)]
    assert "".join(deltas2) == "已经生成好的回复"
    assert isinstance(events2[-1], ChatDone)
    # 关键：模型没有被再调一次
    assert len(service._streamer.calls) == calls_after_first  # type: ignore[attr-defined]
    # 也没有多插一条消息
    assert len(repo.messages.get(session_id, [])) == repo_messages_before + 2


async def test_retry_after_interrupted_stream_continues_generation() -> None:
    """情况 b：上次只落了用户消息、流就断了，重试应继续生成而不是报错。"""
    service, repo, _, _, session_id = await make_service([ChatChunk(delta="续上了")])
    # 模拟「上次用户消息已落库，但助手回复没生成」
    await repo.append_message("u1", session_id, "user", "断掉的消息", "broken-req")

    events = [
        event
        async for event in service.stream_reply(
            "u1", session_id, "断掉的消息", "r2", client_request_id="broken-req"
        )
    ]
    assert isinstance(events[0], ChatMeta)
    deltas = [e.text for e in events if isinstance(e, ChatDelta)]
    assert "".join(deltas) == "续上了"
    # 没有重复插入用户消息：只有原来那条 user + 新生成的 assistant
    roles = [m.role for m in repo.messages.get(session_id, [])]
    assert roles.count("user") == 1


async def test_same_request_id_with_different_content_is_rejected() -> None:
    """同一个 ID 配上不同内容：客户端复用 ID 出错了，应当拒绝。"""
    service, repo, _, _, session_id = await make_service()
    await repo.append_message("u1", session_id, "user", "原来的内容", "dup-req")
    with pytest.raises(AppError) as excinfo:
        await service.stream_reply(
            "u1", session_id, "完全不同的内容", "r2", client_request_id="dup-req"
        ).__anext__()
    assert excinfo.value.code == "DUPLICATE_REQUEST"
