"""统一模型网关：按供应商协议选择适配器，业务代码只依赖这一层。"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from app.infra.llm.adapters.anthropic import AnthropicAdapter
from app.infra.llm.adapters.openai import OpenAICompatibleAdapter
from app.infra.llm.types import (
    ChatChunk,
    ChatParams,
    LLMError,
    Message,
    ModelSpec,
    ProviderConfig,
)


@dataclass(slots=True)
class StreamTelemetry:
    first_token_ms: int | None = None
    total_ms: int | None = None


class LLMGateway:
    """把「接入点 + 模型档案 + 消息」变成一条流。"""

    def __init__(
        self,
        *,
        adapters: dict[str, object] | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._adapters = adapters or {
            "openai": OpenAICompatibleAdapter(timeout_seconds=timeout_seconds),
            "anthropic": AnthropicAdapter(timeout_seconds=timeout_seconds),
        }

    def adapter_for(self, provider: ProviderConfig) -> object:
        try:
            return self._adapters[provider.kind]
        except KeyError as exc:
            raise LLMError(f"未知的供应商协议：{provider.kind}") from exc

    async def astream(
        self,
        provider: ProviderConfig,
        spec: ModelSpec,
        messages: Sequence[Message],
        params: ChatParams,
        *,
        telemetry: StreamTelemetry | None = None,
    ) -> AsyncIterator[ChatChunk]:
        adapter = self.adapter_for(provider)
        started = time.perf_counter()
        first_token_at: float | None = None
        stream = adapter.astream(provider, spec, messages, params)  # type: ignore[attr-defined]
        async for chunk in stream:
            if first_token_at is None and chunk.delta:
                first_token_at = time.perf_counter()
                if telemetry is not None:
                    telemetry.first_token_ms = int((first_token_at - started) * 1000)
            yield chunk
        if telemetry is not None:
            telemetry.total_ms = int((time.perf_counter() - started) * 1000)

    async def probe(
        self,
        provider: ProviderConfig,
        spec: ModelSpec,
        *,
        timeout_seconds: float = 20.0,
    ) -> dict[str, object]:
        """连通性探测：流式返回第一个字即视为可用，并记录首字耗时。"""
        telemetry = StreamTelemetry()
        started = time.perf_counter()
        collected = ""
        params = ChatParams(max_tokens=16)
        async for chunk in self.astream(
            provider,
            spec,
            [Message(role="user", content="ping")],
            params,
            telemetry=telemetry,
        ):
            collected += chunk.delta
            if collected.strip():
                break
        return {
            "ok": True,
            "first_token_ms": telemetry.first_token_ms,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "sample": collected[:80],
        }
