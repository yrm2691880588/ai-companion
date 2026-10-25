"""把 ModelRouter 的流式输出收成一次性文本，供人设生成等非对话任务使用。"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.domain.companions import LLMResult
from app.domain.usage import CallContext, aggregate_usage
from app.infra.llm.gateway import StreamTelemetry
from app.infra.llm.registry import ModelRegistry
from app.infra.llm.router import ModelRouter
from app.infra.llm.types import Message, TaskName, UpstreamError


class RouterLLMClient:
    def __init__(self, router: ModelRouter, registry: ModelRegistry) -> None:
        self._router = router
        self._registry = registry

    async def complete(
        self,
        task: TaskName,
        messages: Sequence[Message],
        *,
        context: CallContext,
    ) -> LLMResult:
        telemetry = StreamTelemetry()
        text = ""
        model_key = ""
        usage_parts = []
        async for chunk in self._router.stream(
            task, messages, telemetry=telemetry, context=context
        ):
            text += chunk.delta
            if chunk.model_key:
                model_key = chunk.model_key
            if chunk.usage is not None:
                usage_parts.append(chunk.usage)
        if not text.strip():
            raise UpstreamError("模型没有返回内容")
        usage = aggregate_usage(usage_parts)
        spec = self._registry.model(model_key) if model_key else None
        cost = self._router.estimated_cost(spec, usage) if spec else Decimal(0)
        return LLMResult(text=text, model_key=model_key, usage=usage, cost_cny=cost)
