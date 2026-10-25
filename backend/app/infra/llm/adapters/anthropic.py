"""Anthropic Messages 协议适配器：DeepSeek 的 /anthropic 兼容入口与 Claude 均可复用。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence

import httpx

from app.infra.llm.adapters.openai import map_http_error
from app.infra.llm.types import (
    ChatChunk,
    ChatParams,
    LLMTimeout,
    MalformedStream,
    Message,
    ModelSpec,
    ProviderConfig,
    Role,
    UpstreamError,
    Usage,
)

ANTHROPIC_VERSION = "2023-06-01"


def split_system(messages: Sequence[Message]) -> tuple[str, list[dict[str, str]]]:
    system_parts: list[str] = []
    dialogue: list[dict[str, str]] = []
    for message in messages:
        if message.role is Role.SYSTEM:
            system_parts.append(message.content)
        else:
            dialogue.append({"role": message.role.value, "content": message.content})
    return "\n\n".join(system_parts), dialogue


class AnthropicAdapter:
    name = "anthropic"

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
        system, dialogue = split_system(messages)
        payload: dict[str, object] = {
            "model": spec.model_name,
            "max_tokens": params.max_tokens or min(spec.max_output, 4096),
            "messages": dialogue,
            "stream": True,
        }
        if system:
            payload["system"] = system
        if params.temperature is not None:
            payload["temperature"] = params.temperature
        if params.top_p is not None:
            payload["top_p"] = params.top_p
        payload.update(params.extra)
        headers = {
            "x-api-key": provider.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
            "accept": "text/event-stream",
        }
        url = provider.base_url.rstrip("/") + "/v1/messages"
        try:
            async with self._client() as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise map_http_error(response.status_code, body)
                    async for line in response.aiter_lines():
                        if not line or line.startswith("event:"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError as exc:
                            raise MalformedStream(f"无法解析流式分片：{data[:120]}") from exc
                        if not isinstance(event, dict):
                            raise MalformedStream("流式分片格式非法")
                        kind = event.get("type")
                        if kind == "content_block_delta":
                            delta = event.get("delta")
                            text = ""
                            if isinstance(delta, dict) and isinstance(delta.get("text"), str):
                                text = delta["text"]
                            yield ChatChunk(delta=text)
                        elif kind == "message_start":
                            message = event.get("message")
                            if isinstance(message, dict):
                                raw_usage = message.get("usage")
                                if isinstance(raw_usage, dict):
                                    prompt = int(raw_usage.get("input_tokens", 0) or 0)
                                    yield ChatChunk(
                                        usage=Usage(
                                            prompt_tokens=prompt,
                                            cache_hit_tokens=int(
                                                raw_usage.get("cache_read_input_tokens", 0) or 0
                                            ),
                                            cache_miss_tokens=prompt,
                                        )
                                    )
                        elif kind == "message_delta":
                            raw_usage = event.get("usage")
                            if isinstance(raw_usage, dict):
                                output = int(raw_usage.get("output_tokens", 0) or 0)
                                yield ChatChunk(
                                    usage=Usage(completion_tokens=output),
                                    finish_reason="stop",
                                )
        except httpx.TimeoutException as exc:
            raise LLMTimeout("请求模型超时") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"网络错误：{exc}") from exc
