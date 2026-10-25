"""OpenAI 兼容协议适配器（DeepSeek、千问、Kimi、GLM、Ollama、vLLM 等通用）。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence

import httpx

from app.infra.llm.types import (
    AuthError,
    Capability,
    ChatChunk,
    ChatParams,
    ContentBlocked,
    ContextOverflow,
    LLMError,
    LLMTimeout,
    MalformedStream,
    Message,
    ModelSpec,
    ProviderConfig,
    RateLimited,
    UpstreamError,
    Usage,
)

_CONTEXT_HINTS = ("context length", "maximum context", "too many tokens", "context_length_exceeded")
_CONTENT_HINTS = ("content filter", "content_policy", "safety", "moderation", "sensitive")


def _decode(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def map_http_error(status: int, body: bytes) -> LLMError:
    text = _decode(body)
    lowered = text.lower()
    if status in (401, 403):
        return AuthError(f"鉴权失败：{text[:200]}", status=status)
    if status == 429:
        return RateLimited(f"触发限流：{text[:200]}", status=status)
    if status in (400, 413, 422):
        if any(hint in lowered for hint in _CONTEXT_HINTS):
            return ContextOverflow(f"上下文超限：{text[:200]}", status=status)
        if any(hint in lowered for hint in _CONTENT_HINTS):
            return ContentBlocked(f"上游内容拦截：{text[:200]}", status=status)
    if status >= 500:
        return UpstreamError(f"上游错误 {status}：{text[:200]}", status=status)
    return UpstreamError(f"请求被拒绝 {status}：{text[:200]}", status=status)


def _thinking_payload(
    provider: ProviderConfig, spec: ModelSpec, params: ChatParams
) -> dict[str, object]:
    """思考模式开关按厂商写法注入；默认显式关闭，避免账单里冒出思考 token。"""
    if provider.thinking_style == "deepseek" and Capability.THINKING in spec.supports:
        return {"thinking": {"type": "enabled" if params.thinking else "disabled"}}
    return {}


def build_payload(
    provider: ProviderConfig,
    spec: ModelSpec,
    messages: Sequence[Message],
    params: ChatParams,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": spec.model_name,
        "messages": [{"role": m.role.value, "content": m.content} for m in messages],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if params.temperature is not None:
        payload["temperature"] = params.temperature
    if params.max_tokens is not None:
        payload["max_tokens"] = params.max_tokens
    if params.json_mode:
        payload["response_format"] = {"type": "json_object"}
    payload.update(_thinking_payload(provider, spec, params))
    payload.update(params.extra)
    return payload


def parse_usage(raw: object) -> Usage | None:
    if not isinstance(raw, dict):
        return None
    hit = raw.get("prompt_cache_hit_tokens")
    miss = raw.get("prompt_cache_miss_tokens")
    prompt = int(raw.get("prompt_tokens", 0) or 0)
    completion = int(raw.get("completion_tokens", 0) or 0)
    if hit is None and miss is None:
        hit, miss = 0, prompt
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        cache_hit_tokens=int(hit or 0),
        cache_miss_tokens=int(miss or 0),
    )


class OpenAICompatibleAdapter:
    """按 OpenAI ChatCompletions 协议流式调用；SSE 逐行解析。"""

    name = "openai"

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._transport = transport
        self._timeout = timeout_seconds

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(self._timeout, connect=10.0),
        )

    async def astream(
        self,
        provider: ProviderConfig,
        spec: ModelSpec,
        messages: Sequence[Message],
        params: ChatParams,
    ) -> AsyncIterator[ChatChunk]:
        url = provider.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        payload = build_payload(provider, spec, messages, params)
        try:
            async with self._client() as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise map_http_error(response.status_code, body)
                    async for line in response.aiter_lines():
                        if not line or line.startswith(":"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            return
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError as exc:  # 供应商偶发脏行
                            raise MalformedStream(f"无法解析流式分片：{data[:120]}") from exc
                        if not isinstance(event, dict):
                            raise MalformedStream("流式分片格式非法")
                        usage = parse_usage(event.get("usage"))
                        choices = event.get("choices")
                        if isinstance(choices, list) and choices:
                            choice = choices[0]
                            if not isinstance(choice, dict):
                                raise MalformedStream("choices 格式非法")
                            delta = choice.get("delta")
                            text = ""
                            if isinstance(delta, dict):
                                raw_text = delta.get("content")
                                if isinstance(raw_text, str):
                                    text = raw_text
                            yield ChatChunk(
                                delta=text,
                                finish_reason=choice.get("finish_reason"),
                                usage=usage,
                            )
                        elif usage is not None:
                            yield ChatChunk(delta="", usage=usage, finish_reason="stop")
        except httpx.TimeoutException as exc:
            raise LLMTimeout("请求模型超时") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"网络错误：{exc}") from exc
