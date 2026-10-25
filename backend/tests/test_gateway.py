import json

import httpx
import pytest

from app.infra.llm.adapters.openai import OpenAICompatibleAdapter
from app.infra.llm.pricing import parse_banded_price
from app.infra.llm.types import (
    AuthError,
    Capability,
    ChatParams,
    ContextOverflow,
    Message,
    ModelSpec,
    ProviderConfig,
    RateLimited,
    Role,
    UpstreamError,
)

PRICE = parse_banded_price(
    {
        "hit": {"peak": 0.04, "offpeak": 0.02},
        "miss": {"peak": 2.0, "offpeak": 1.0},
        "out": {"peak": 8.0, "offpeak": 4.0},
    }
)


def spec() -> ModelSpec:
    return ModelSpec(
        key="deepseek:deepseek-flash",
        provider_key="deepseek",
        model_name="deepseek-flash",
        display_name="DeepSeek V4.1 Flash",
        context_window=1_000_000,
        max_output=384_000,
        supports=frozenset({Capability.STREAM, Capability.THINKING}),
        price=PRICE,
    )


def provider() -> ProviderConfig:
    return ProviderConfig(
        key="deepseek",
        name="DeepSeek",
        kind="openai",
        base_url="https://api.deepseek.com",
        api_key="sk-test",
        thinking_style="deepseek",
    )


def sse(*events: dict[str, object]) -> str:
    body = "".join(f"data: {json.dumps(event, ensure_ascii=False)}\n\n" for event in events)
    return body + "data: [DONE]\n\n"


def transport(
    body: str,
    *,
    status: int = 200,
    captured: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        return httpx.Response(
            status,
            content=body.encode("utf-8"),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    return httpx.MockTransport(handler)


async def collect(adapter: OpenAICompatibleAdapter) -> list:
    messages = [Message(role=Role.USER, content="你好")]
    chunks = []
    async for chunk in adapter.astream(provider(), spec(), messages, ChatParams(max_tokens=16)):
        chunks.append(chunk)
    return chunks


async def test_stream_deltas_and_usage() -> None:
    body = sse(
        {"choices": [{"delta": {"content": "你"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "好"}, "finish_reason": "stop"}]},
        {
            "choices": [],
            "usage": {
                "prompt_tokens": 1200,
                "completion_tokens": 2,
                "prompt_cache_hit_tokens": 1000,
                "prompt_cache_miss_tokens": 200,
            },
        },
    )
    adapter = OpenAICompatibleAdapter(transport=transport(body))
    chunks = await collect(adapter)
    assert "".join(chunk.delta for chunk in chunks) == "你好"
    usage = [chunk.usage for chunk in chunks if chunk.usage][-1]
    assert usage.prompt_tokens == 1200
    assert usage.cache_hit_tokens == 1000
    assert usage.cache_miss_tokens == 200
    assert usage.hit_ratio == pytest.approx(1000 / 1200)


async def test_request_shape() -> None:
    captured: list[httpx.Request] = []
    body = sse({"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]})
    adapter = OpenAICompatibleAdapter(transport=transport(body, captured=captured))
    await collect(adapter)
    request = captured[0]
    assert request.url == "https://api.deepseek.com/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test"
    payload = json.loads(request.content)
    assert payload["model"] == "deepseek-flash"
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    # 默认显式关闭思考模式，避免思考 token 进账单
    assert payload["thinking"] == {"type": "disabled"}


async def test_thinking_mode_can_be_enabled_explicitly() -> None:
    captured: list[httpx.Request] = []
    body = sse({"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]})
    adapter = OpenAICompatibleAdapter(transport=transport(body, captured=captured))
    messages = [Message(role=Role.USER, content="hi")]
    async for _ in adapter.astream(provider(), spec(), messages, ChatParams(thinking=True)):
        pass
    payload = json.loads(captured[0].content)
    assert payload["thinking"] == {"type": "enabled"}


async def test_rate_limit_is_mapped() -> None:
    adapter = OpenAICompatibleAdapter(transport=transport("{}", status=429))
    with pytest.raises(RateLimited):
        await collect(adapter)


async def test_context_overflow_is_mapped() -> None:
    body = json.dumps({"error": {"message": "This model's maximum context length is 1000000"}})
    adapter = OpenAICompatibleAdapter(transport=transport(body, status=400))
    with pytest.raises(ContextOverflow):
        await collect(adapter)


async def test_auth_error_is_mapped() -> None:
    adapter = OpenAICompatibleAdapter(transport=transport("{}", status=401))
    with pytest.raises(AuthError):
        await collect(adapter)


async def test_upstream_error_is_mapped() -> None:
    adapter = OpenAICompatibleAdapter(transport=transport("{}", status=503))
    with pytest.raises(UpstreamError):
        await collect(adapter)


async def test_usage_without_cache_fields_falls_back_to_prompt() -> None:
    body = sse(
        {"choices": [{"delta": {"content": "a"}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 50, "completion_tokens": 1}},
    )
    adapter = OpenAICompatibleAdapter(transport=transport(body))
    chunks = await collect(adapter)
    usage = [chunk.usage for chunk in chunks if chunk.usage][-1]
    assert usage.cache_hit_tokens == 0
    assert usage.cache_miss_tokens == 50
