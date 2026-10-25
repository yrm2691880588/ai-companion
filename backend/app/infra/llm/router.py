"""模型路由：任务 → 模型链 → 预算 → 流式调用（仅首 token 前允许降级）。"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.domain.usage import CallContext, CallRecord, UsageRecorder, aggregate_usage
from app.infra.llm.gateway import LLMGateway, StreamTelemetry
from app.infra.llm.pricing import TimeBand, budget_tokens, time_band, turn_cost
from app.infra.llm.registry import ModelRegistry, RouteStep
from app.infra.llm.tokenizer import fit_messages
from app.infra.llm.types import (
    AllProvidersFailed,
    Capability,
    ChatChunk,
    ChatParams,
    ContentBlocked,
    ContextOverflow,
    LLMError,
    Message,
    ModelSpec,
    ProviderConfig,
    StreamAborted,
    TaskName,
    UpstreamError,
    Usage,
)

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PlannedCall:
    step: RouteStep
    spec: ModelSpec
    provider: ProviderConfig


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class ModelRouter:
    """把「任务」翻译成一次可降级的流式调用。"""

    def __init__(
        self,
        registry: ModelRegistry,
        gateway: LLMGateway,
        *,
        turn_cost_cap_cny: float = 0.02,
        hit_ratio: float = 0.85,
        expected_output_tokens: int = 500,
        max_context_ratio: float = 0.8,
        clock: Callable[[], datetime] | None = None,
        recorder: UsageRecorder | None = None,
        overrides: Callable[[str], dict[str, object] | None] | None = None,
    ) -> None:
        self.registry = registry
        self.gateway = gateway
        self.turn_cost_cap_cny = turn_cost_cap_cny
        self.hit_ratio = hit_ratio
        self.expected_output_tokens = expected_output_tokens
        self.max_context_ratio = max_context_ratio
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._recorder = recorder
        self._overrides = overrides

    # ---------- 规划 ----------
    def band(self) -> TimeBand:
        return time_band(self._clock())

    def plan(
        self,
        task: TaskName | str,
        *,
        required: frozenset[Capability] = frozenset({Capability.STREAM}),
    ) -> list[PlannedCall]:
        calls: list[PlannedCall] = []
        for step in self.registry.resolve(task, required=required):
            spec = self.registry.model(step.model_key)
            provider = self.registry.provider(spec.provider_key)
            calls.append(PlannedCall(step=step, spec=spec, provider=provider))
        return self._apply_override(task, calls)

    def _apply_override(self, task: TaskName | str, calls: list[PlannedCall]) -> list[PlannedCall]:
        """管理员统一配置：指定模型优先、参数覆盖主模型。"""
        if self._overrides is None or not calls:
            return calls
        task_key = task.value if isinstance(task, TaskName) else str(task)
        try:
            override = self._overrides(task_key)
        except Exception:
            override = None
        if not override:
            return calls
        model_key = str(override.get("model") or "")
        if model_key:
            matching = [item for item in calls if item.spec.key == model_key]
            rest = [item for item in calls if item.spec.key != model_key]
            if matching:
                calls = matching + rest
            elif model_key in self.registry.models:
                try:
                    spec = self.registry.model(model_key)
                    provider = self.registry.provider(spec.provider_key)
                    calls = [
                        PlannedCall(
                            step=RouteStep(model_key=model_key, params={}),
                            spec=spec,
                            provider=provider,
                        ),
                        *calls,
                    ]
                except KeyError:
                    pass
        first = calls[0]
        merged_params = dict(first.step.params)
        for field in ("temperature", "max_tokens", "top_p", "thinking", "json_mode"):
            if field in override and override[field] is not None:
                merged_params[field] = override[field]
        calls[0] = PlannedCall(
            step=RouteStep(model_key=first.spec.key, params=merged_params),
            spec=first.spec,
            provider=first.provider,
        )
        return calls

    def budget(self, spec: ModelSpec, *, band: TimeBand | None = None) -> int:
        price = spec.price.for_band(band or self.band())
        return budget_tokens(
            price,
            cap_cny=self.turn_cost_cap_cny,
            hit_ratio=self.hit_ratio,
            expected_output_tokens=self.expected_output_tokens,
            context_window=spec.context_window,
            max_context_ratio=self.max_context_ratio,
        )

    def estimated_cost(
        self,
        spec: ModelSpec,
        usage: Usage,
        *,
        band: TimeBand | None = None,
    ) -> Decimal:
        price = spec.price.for_band(band or self.band())
        # 以供应商返回的命中/未命中 token 为准；不报缓存的供应商按未命中价算（保守）
        return turn_cost(
            price,
            input_tokens=usage.input_tokens,
            output_tokens=usage.completion_tokens,
            hit_ratio=usage.hit_ratio,
        )

    # ---------- 调用 ----------
    def _params(self, call: PlannedCall, override: ChatParams | None) -> ChatParams:
        raw = call.step.params
        top_p_raw = raw.get("top_p")
        params = ChatParams(
            temperature=_as_float(raw.get("temperature"), 0.8),
            max_tokens=min(_as_int(raw.get("max_tokens"), 512), call.spec.max_output),
            top_p=float(top_p_raw) if isinstance(top_p_raw, (int, float)) else None,
            thinking=bool(raw.get("thinking", False)),
            json_mode=bool(raw.get("json_mode", False)),
        )
        if override is None:
            return params
        return ChatParams(
            temperature=override.temperature
            if override.temperature is not None
            else params.temperature,
            max_tokens=override.max_tokens or params.max_tokens,
            top_p=override.top_p if override.top_p is not None else params.top_p,
            thinking=override.thinking or params.thinking,
            json_mode=override.json_mode or params.json_mode,
            extra={**params.extra, **override.extra},
        )

    @staticmethod
    def _tag(chunk: ChatChunk, call: PlannedCall) -> ChatChunk:
        return ChatChunk(
            delta=chunk.delta,
            finish_reason=chunk.finish_reason,
            usage=chunk.usage,
            model_key=call.spec.key,
            provider_key=call.spec.provider_key,
        )

    async def _record(
        self,
        context: CallContext | None,
        call: PlannedCall,
        attempt_no: int,
        status: str,
        usage: Usage,
        started_at: float,
        telemetry: StreamTelemetry | None,
        error_code: str | None = None,
    ) -> None:
        if self._recorder is None or context is None:
            return
        cost = self.estimated_cost(call.spec, usage)
        task_value = context.task.value if isinstance(context.task, TaskName) else str(context.task)
        record = CallRecord(
            user_id=context.user_id,
            task=task_value,
            request_id=context.request_id,
            provider_key=call.spec.provider_key,
            model_key=call.spec.key,
            attempt_no=attempt_no,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cache_hit_tokens=usage.cache_hit_tokens,
            cache_miss_tokens=usage.cache_miss_tokens,
            cost_micros=int(cost * Decimal(1_000_000)),
            first_token_ms=telemetry.first_token_ms if telemetry else None,
            total_ms=int((time.perf_counter() - started_at) * 1000),
            status=status,
            error_code=error_code,
            created_at=datetime.now(UTC),
        )
        try:
            await self._recorder.save(record)
        except Exception:  # 记账失败不能影响用户对话
            _LOG.exception(
                "写入 llm_calls 失败 request_id=%s model=%s", context.request_id, call.spec.key
            )

    async def stream(
        self,
        task: TaskName | str,
        messages: Sequence[Message],
        *,
        required: frozenset[Capability] = frozenset({Capability.STREAM}),
        params_override: ChatParams | None = None,
        telemetry: StreamTelemetry | None = None,
        context: CallContext | None = None,
    ) -> AsyncIterator[ChatChunk]:
        plans = self.plan(task, required=required)
        if not plans:
            raise AllProvidersFailed([("", "没有满足能力要求的模型")])
        band = self.band()
        attempts: list[tuple[str, str]] = []
        attempt_no = 0

        for index, call in enumerate(plans):
            budget = self.budget(call.spec, band=band)
            fitted = fit_messages(messages, budget)
            params = self._params(call, params_override)
            overflow_retried = False
            while True:
                attempt_no += 1
                attempt_started = time.perf_counter()
                usage_parts: list[Usage] = []
                stream = self.gateway.astream(
                    call.provider, call.spec, fitted, params, telemetry=telemetry
                )
                try:
                    first = await anext(stream)
                except StopAsyncIteration:
                    attempts.append((call.spec.key, "EMPTY_STREAM"))
                    await self._record(
                        context,
                        call,
                        attempt_no,
                        "error",
                        Usage(),
                        attempt_started,
                        telemetry,
                        "EMPTY_STREAM",
                    )
                    if index + 1 < len(plans):
                        break
                    raise UpstreamError("模型返回了空响应") from None
                except ContextOverflow as exc:
                    await self._record(
                        context,
                        call,
                        attempt_no,
                        "error",
                        Usage(),
                        attempt_started,
                        telemetry,
                        exc.code,
                    )
                    if overflow_retried:
                        attempts.append((call.spec.key, exc.code))
                        break
                    overflow_retried = True
                    fitted = fit_messages(messages, max(budget // 2, 512))
                    continue
                except ContentBlocked as exc:
                    # 内容拦截不换供应商，交给安全话术
                    await self._record(
                        context,
                        call,
                        attempt_no,
                        "blocked",
                        Usage(),
                        attempt_started,
                        telemetry,
                        exc.code,
                    )
                    raise
                except LLMError as exc:
                    await self._record(
                        context,
                        call,
                        attempt_no,
                        "error",
                        Usage(),
                        attempt_started,
                        telemetry,
                        exc.code,
                    )
                    attempts.append((call.spec.key, exc.code))
                    if exc.retryable:
                        break
                    raise
                # 首 token 到手：此后不再降级
                if first.usage is not None:
                    usage_parts.append(first.usage)
                yield self._tag(first, call)
                try:
                    async for chunk in stream:
                        if chunk.usage is not None:
                            usage_parts.append(chunk.usage)
                        yield self._tag(chunk, call)
                except ContentBlocked as exc:
                    await self._record(
                        context,
                        call,
                        attempt_no,
                        "blocked",
                        aggregate_usage(usage_parts),
                        attempt_started,
                        telemetry,
                        exc.code,
                    )
                    raise
                except LLMError as exc:
                    await self._record(
                        context,
                        call,
                        attempt_no,
                        "aborted",
                        aggregate_usage(usage_parts),
                        attempt_started,
                        telemetry,
                        exc.code,
                    )
                    raise StreamAborted(f"生成中断：{exc.code}") from exc
                await self._record(
                    context,
                    call,
                    attempt_no,
                    "ok",
                    aggregate_usage(usage_parts),
                    attempt_started,
                    telemetry,
                )
                return

        raise AllProvidersFailed(attempts)
